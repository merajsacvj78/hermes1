"""Offline stand-in for the Telegram Bot API.

Network egress to api.telegram.org is blocked in this sandbox, so boot checks
point the bot at this server via TELEGRAM_API_BASE. It answers just enough of
the API surface for aiogram to start polling.
"""
from aiohttp import web

MSG = {"message_id": 1, "date": 0,
       "chat": {"id": -500, "type": "supergroup"}, "text": "x"}


def ok(result):
    return web.json_response({"ok": True, "result": result})


async def handle(req):
    method = req.match_info["method"]
    if method == "getMe":
        return ok({"id": 1, "is_bot": True, "first_name": "VCORP",
                   "username": "vcorp_outbreak_bot", "can_join_groups": True,
                   "can_read_all_group_messages": False,
                   "supports_inline_queries": False})
    if method == "getUpdates":
        return ok([])
    if method == "sendDice":
        return ok({**MSG, "dice": {"emoji": "🎯", "value": 4}})
    if method in ("sendMessage", "editMessageText", "editMessageReplyMarkup",
                  "sendAnimation", "sendSticker", "copyMessage",
                  "sendPhoto", "editMessageCaption"):
        return ok(MSG)
    if method == "getMyName":
        return ok({"name": "V-CORP: OUTBREAK"})
    return ok(True)          # setMyCommands, deleteWebhook, ... -> true


app = web.Application()
app.router.add_route("*", "/bot{token}/{method}", handle)

if __name__ == "__main__":
    web.run_app(app, host="127.0.0.1", port=8084, print=None)
