# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2021-2022 Hitalo M. <https://github.com/HitaloM>

from typing import List

import httpx
from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from androidrepo.bot import AndroidRepo
from androidrepo.database.xposed import create_lsposed, get_lsposed_by_branch
from androidrepo.modules.utils import get_changelog
from androidrepo.modules.utils.xposed import get_lsposed

TYPES: List[str] = ["riru", "zygisk"]


@AndroidRepo.on_message(filters.cmd("lsposed"))
async def lsposed(c: AndroidRepo, m: Message):
    command = m.text.split()[0]
    branch = m.text[len(command) :]

    sm = await m.reply("Checking...")

    branch = "zygisk" if len(branch) < 1 else branch[1:]
    branch = branch.lower()

    if branch not in TYPES:
        await sm.edit(f"The version type '<b>{branch}</b>' was not found.")
        return

    _lsposed = await get_lsposed_by_branch(branch=branch)
    if _lsposed is None:
        async with httpx.AsyncClient(
            http2=True, timeout=40, follow_redirects=True
        ) as client:
            r = await client.get(
                f"https://lsposed.github.io/LSPosed/release/{branch}.json"
            )
            lsposed = r.json()
            await client.aclose()
        changelog = await get_changelog(lsposed["changelog"])
        await create_lsposed(
            branch=branch,
            version=lsposed["version"],
            version_code=lsposed["versionCode"],
            link=lsposed["zipUrl"],
            changelog=changelog,
        )
        _lsposed = await get_lsposed_by_branch(branch=branch)

    text = f"<b>{branch.capitalize()} - LSPosed</b>"
    text += f"\n\n<b>Version</b>: <code>{_lsposed['version']}</code> (<code>{_lsposed['version_code']}</code>)"
    text += f"\n<b>Changelog</b>: {_lsposed['changelog']}"

    keyboard = [[("⬇️ Download", _lsposed["link"], "url")]]

    await sm.edit_text(
        text,
        reply_markup=c.ikb(keyboard),
        parse_mode=ParseMode.DEFAULT,
        disable_web_page_preview=True,
    )


@AndroidRepo.on_message(filters.sudo & filters.cmd("lsposeds"))
async def lsposeds(c: AndroidRepo, m: Message):
    return await get_lsposed(m)
