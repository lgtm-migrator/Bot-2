# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2021-2022 Hitalo M. <https://github.com/HitaloM>

import asyncio
import logging

from pyrogram import idle
from pyrogram.session import Session

from androidrepo.bot import AndroidRepo, log
from androidrepo.database import database
from androidrepo.utils import is_windows

# Custom logging format
logging.basicConfig(
    level=logging.INFO,
    format="%(name)s.%(funcName)s | %(levelname)s | %(message)s",
    datefmt="[%X]",
)


# To avoid some pyrogram annoying log
logging.getLogger("pyrogram.syncer").setLevel(logging.WARNING)
logging.getLogger("pyrogram.client").setLevel(logging.WARNING)
logging.getLogger("aiodown").setLevel(logging.WARNING)


# Use uvloop to improve speed if available
try:
    import uvloop

    uvloop.install()
except ImportError:
    if not is_windows():
        log.warning("uvloop is not installed and therefore will be disabled.")


# Disable ugly pyrogram notice print
Session.notice_displayed = True


async def main() -> None:
    await database.connect()

    ar = AndroidRepo()
    await ar.start()
    await idle()
    await ar.stop()

    if database.is_connected:
        await database.close()


if __name__ == "__main__":
    # open new asyncio event loop
    event_policy = asyncio.get_event_loop_policy()
    event_loop = event_policy.new_event_loop()
    try:
        # start the sqlite database and pyrogram client
        event_loop.run_until_complete(main())
    except KeyboardInterrupt:
        # exit gracefully
        log.warning("Forced stop... Bye!")
    finally:
        # close asyncio event loop
        event_loop.close()
