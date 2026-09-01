import json

config_path = "/etc/onlyoffice/documentserver/local.json"

with open(config_path, "r", encoding="utf-8") as f:
    config = json.load(f)

# 1. services.CoAuthoring.request-filtering-agent
services = config.setdefault("services", {})
co_authoring = services.setdefault("CoAuthoring", {})
filter_agent = co_authoring.setdefault("request-filtering-agent", {})
filter_agent["allowPrivateIPAddress"] = True
filter_agent["allowMetaIPAddress"] = True

# 2. externalRequest.action.blockPrivateIP
ext_req = config.setdefault("externalRequest", {})
action = ext_req.setdefault("action", {})
action["allow"] = True
action["blockPrivateIP"] = False

with open(config_path, "w", encoding="utf-8") as f:
    json.dump(config, f, indent=2)

print("SUCCESS_ACCURATELY_CONFIG_UPDATED")
