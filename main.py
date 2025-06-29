import json
import asyncio
import logging
from typing import Any, Union

import flask
import requests
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_ollama import ChatOllama
# https://gaodalie.substack.com/p/langchain-mcp-rag-ollama-the-key
app = flask.Flask("mcp-proxy")

excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
toolable_paths = ['api/chat']


def mcp_call_tool(name:str, args: dict[str, Any] = {}) -> Any:
    logging.info(f"Calling tool {name} with args {args}")
    for tool in tools:
        if tool.name == name:
            return asyncio.run(tool.ainvoke(args))


def mcp_call_tools(tool_calls: list[dict[str, Any]] = []) -> list[Any]:
    result = []
    for tool_call in tool_calls:
        func_call = tool_call.get("function", None)
        if func_call:
            result.append(mcp_call_tool(func_call["name"], func_call["arguments"]))
    return result


def stream_response(res):
    tool_calls = []
    for line in res.iter_lines():
        if line:
            line = line.decode('utf-8')
            logging.info(f"Line {line}")
            js = json.loads(line)
            req_tool_calls = js.get("message", {}).get("tool_calls")
            if req_tool_calls:
                tool_calls = tool_calls + req_tool_calls
            yield f"data: {line}\n\n"

    mcp_call_tools(tool_calls)


def proxy_request(subpath: str,
                  data: Union[str, dict[str, Any]] = None,
                  method: str = None,
                  headers: dict[str, str] = None,
                  cookies: list[str] = None,
                  stream: bool = False) -> requests.Response:
    if data is None:
        data = flask.request.get_data()
    if data is not None and isinstance(data, dict):
        data = jsonify(data)
    if method is None:
        method = flask.request.method
    if headers is None:
        headers = {k: v for k, v in flask.request.headers if k.lower() != 'host'}
    if cookies is None:
        cookies = flask.request.cookies

    url = f"{config['ollama']['url']}/{subpath}"

    logging.info(f"""Sending request :
- method={method}
- url={url}
- headers={headers}
- cookies={cookies}
- data
{data}""")

    return requests.request(
        method=method,
        url=url,
        headers=headers,
        data=data,
        cookies=cookies,
        allow_redirects=True,
        stream=stream
    )


def merge_tools(data_json: dict[str, Any]) -> dict[str, Any]:
    req_tools = data_json.get("tools", [])
    req_tools = req_tools + ollama_tools

    logging.debug(f"Adding tools to request : {data_json}")
    data_json["tools"] = req_tools

    return data_json


def filter_headers(headers: dict[str, Any]) -> dict[str, Any]:
    return [(k, v) for k, v in headers.items() if k.lower() not in excluded_headers]


def log_flask_request():
    logging.debug(f"""=== REQUEST ===
-- Headers
{jsonify({k: v for k, v in flask.request.headers})}
-- Body
{flask.request.get_data()}
""")


def log_response(response):
    logging.debug(f"""=== RESPONSE ===
-- Headers
{jsonify(response.raw.headers.items())}
-- Body
{response.content}
""")


def process_ollama_toolable_request(subpath: str) -> flask.Response:
    data = flask.request.get_data()

    data_json = merge_tools(json.loads(data))
    stream = data_json.get("stream", False)

    while True:
        res = proxy_request(subpath, data=data_json)

        log_response(res)

        try:
            json_response = res.json()
        except:
            logging.info("Response is not json, sending as-is")
            break

        tool_calls = json_response.get("message", {}).get("tool_calls")
        if not tool_calls:
            logging.info("Backend did not call tools, sending as-is")
            break

        # Ajoute la demande d'appel d'outil à l'historique
        messages = data_json.get("messages", [])
        messages.append(json_response.get("message", {}))

        # Ajoute la réponse des outils à l'historique
        tool_responses = mcp_call_tools(tool_calls)
        for tool_response in tool_responses:
            messages.append({
                "role": "tool",
                "content": tool_response
            })

    return flask.Response(res.content, res.status_code, filter_headers(res.raw.headers))


@app.route("/<path:subpath>", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
def ollama_default(subpath: str):
    log_flask_request()

    if subpath in toolable_paths:
        return process_ollama_toolable_request(subpath)

    res = proxy_request(subpath, flask.request.get_data())
    log_response(res)

    return flask.Response(res.content, res.status_code, filter_headers(res.raw.headers))


def jsonify(ob):
    return json.dumps(ob, indent=2, default=lambda o: o.__dict__)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    with open("config.js", "r") as f:
        config = json.load(f)

    mcp = MultiServerMCPClient(config["mcp"])
    tools = asyncio.run(mcp.get_tools())
    ollama_binding = ChatOllama(model='no-model').bind_tools(tools)
    ollama_tools = ollama_binding.kwargs["tools"]
    app.run(host="127.0.0.1", port=48001, debug=True)


