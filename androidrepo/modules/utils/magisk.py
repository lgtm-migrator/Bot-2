# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2021-2022 Hitalo M. <https://github.com/HitaloM>

import asyncio
import contextlib
import io
import os
import shutil
from datetime import datetime
from typing import Dict, List
from zipfile import ZipFile

import aiodown
import httpx
import rapidjson as json
from github import Github
from github.GithubException import UnknownObjectException
from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from androidrepo import config
from androidrepo.database.magisk import (
    create_magisk,
    create_module,
    delete_module,
    get_all_magisk,
    get_all_modules,
    get_magisk_by_branch,
    get_module_by_id,
    update_magisk_from_dict,
    update_module_by_dict,
)
from androidrepo.modules.utils import get_changelog

DOWNLOAD_DIR: str = "./downloads/"
MAGISK_URL: str = "https://github.com/topjohnwu/magisk-files/raw/master/{}.json"

github = Github(config.GITHUB_TOKEN)
user = github.get_user("Magisk-Modules-Repo")
repos = user.get_repos()


async def check_modules(c: Client):
    date = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")
    modules = {"list": []}
    updated_modules = []
    excluded_modules = []
    for repo in repos:
        try:
            module_prop = repo.get_contents("module.prop").decoded_content.decode(
                "utf-8"
            )
            module = await parse_module(module_prop)
            module[
                "url"
            ] = f"https://github.com/{repo.full_name}/archive/{repo.default_branch}.zip"
            commit_sha = repo.get_commits()[0].sha
            commit = repo.get_commit(sha=commit_sha)
            commit_date = commit.commit.committer.date
            module["last_update"] = int(commit_date.timestamp() * 1000)
            modules["list"].append(module)
            _module = await get_module_by_id(id=module["id"])
            if not _module:
                await create_module(
                    id=module["id"],
                    url=module["url"],
                    name=module["name"],
                    version=module["version"],
                    version_code=module["versionCode"],
                    last_update=module["last_update"],
                )
                continue
        except UnknownObjectException:
            continue

        if _module["version"] != module["version"] or int(
            _module["version_code"]
        ) != int(module["versionCode"]):
            updated_modules.append(module)
            await asyncio.sleep(2)
            await update_module(c, module)

    module_ids = list(map(lambda module: module["id"], modules["list"]))
    for _module in await get_all_modules():
        if _module["id"] not in module_ids:
            excluded_modules.append(_module)
            for index, module in enumerate(modules["list"]):
                if _module["id"] == module["id"]:
                    del modules["list"][index]
            await delete_module(id=_module["id"])
    if updated_modules or excluded_modules:
        await c.send_log_message(
            config.LOGS_ID,
            f"""
<b>Magisk Modules check finished</b>
    <b>Found</b>: <code>{len(modules["list"])}</code>
    <b>Updated</b>: <code>{len(updated_modules)}</code>
    <b>Excluded</b>: <code>{len(excluded_modules)}</code>

<b>Date</b>: <code>{date}</code>
#Sync #Magisk #Modules
    """,
        )
    return


async def get_modules(m: Message):
    date = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")
    modules = await get_all_modules()
    modules_list = []
    if len(modules) > 0:
        modules_list.extend(
            dict(
                id=module["id"],
                url=module["url"],
                name=module["name"],
                version=module["version"],
                version_code=module["version_code"],
                last_update=module["last_update"],
            )
            for module in modules
        )

        document = io.BytesIO(str(json.dumps(modules_list, indent=4)).encode())
        document.name = "modules.json"
        return await m.reply_document(
            caption=f"<b>Magisk Modules</b>\n<b>Modules count</b>: <code>{len(modules)}</code>\n<b>Date</b>: <code>{date}</code>",
            document=document,
        )

    return await m.reply_text("No modules were found.")


async def get_magisk(m: Message):
    date = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")
    magisks = await get_all_magisk()
    magisks_list = []
    if len(magisks) > 0:
        magisks_list.extend(
            dict(
                branch=magisk["branch"],
                version=magisk["version"],
                versionCode=magisk["version_code"],
                link=magisk["link"],
                note=magisk["note"],
                changelog=magisk["changelog"],
            )
            for magisk in magisks
        )

        document = io.BytesIO(str(json.dumps(magisks_list, indent=4)).encode())
        document.name = "magisk.json"
        return await m.reply_document(
            caption=f"<b>Magisk Releases</b>\n<b>Date</b>: <code>{date}</code>",
            document=document,
        )

    return await m.reply_text("No Magisks found.")


async def parse_module(data: str) -> Dict:
    module: Dict = {}
    for line in data.splitlines():
        try:
            key, value = line.split("=", 1)
            if key in [
                "id",
                "author",
                "description",
                "name",
                "version",
                "versionCode",
                "updateJson",
            ]:
                module[key] = value
        except BaseException:
            continue
    return module


async def update_module(c: Client, module: Dict):
    file_name = (
        (
            (
                (
                    (
                        (
                            module["name"]
                            .replace("-", "")
                            .replace(" ", "-")
                            .replace("--", "")
                            + "_"
                        )
                        + module["version"]
                    )
                    + "_"
                )
                + "("
            )
            + module["versionCode"]
        )
        + ")"
    ) + ".zip"

    file_path = DOWNLOAD_DIR + file_name
    async with aiodown.Client() as client:
        download = client.add(module["url"], file_path)
        await client.start()
        while not download.is_finished():
            await asyncio.sleep(0.5)
        if download.get_status() == "failed":
            return
    files = []
    extraction_path = None
    with ZipFile(file_path, "r") as old_zip:
        for file in old_zip.namelist():
            if extraction_path is None:
                extraction_path = DOWNLOAD_DIR + "/".join(file.split("/")[:3])
            path = DOWNLOAD_DIR + file
            files.append(path)
            old_zip.extract(member=file, path=DOWNLOAD_DIR)
        old_zip.close()
    os.remove(file_path)
    with ZipFile(file_path, "w") as new_zip:
        for file in files:
            name = "/".join(file.split("/")[3:])
            if name not in [" ", ""] and not name.startswith("."):
                new_zip.write(file, name)
        new_zip.close()
    with contextlib.suppress(BaseException):
        shutil.rmtree(extraction_path)
    caption = f"""
<b>{module["name"]} {"v" if module["version"][0].isdecimal() else ""}{module["version"]} ({module["versionCode"]})</b>

⚡<i>Magisk Module</i>
⚡<i>{module["description"]}</i>
⚡️<a href="https://github.com/Magisk-Modules-Repo/{module["id"]}">GitHub Repository</a>

<b>By:</b> {module["author"]}
<b>Follow:</b> @AndroidRepo
    """

    await c.send_channel_document(
        caption=caption, document=file_path, force_document=True
    )

    os.remove(file_path)
    await update_module_by_dict(
        id=module["id"],
        data={
            "description": module["description"],
            "name": module["name"],
            "version_code": module["versionCode"],
            "version": module["version"],
            "last_update": module["last_update"],
        },
    )


async def check_magisk(c: Client):
    TYPES: List[str] = ["stable", "beta", "canary"]
    for magisk in TYPES:
        await update_magisk(c, magisk)


async def update_magisk(c: Client, m_type: str):
    date = datetime.now().strftime("%H:%M:%S - %d/%m/%Y")
    URL = MAGISK_URL.format(m_type)
    async with httpx.AsyncClient(
        http2=True, timeout=40, follow_redirects=True
    ) as client:
        response = await client.get(URL)
        data = response.json()
        magisk = data["magisk"]
        _magisk = await get_magisk_by_branch(branch=m_type)
        if _magisk is None:
            chg = await get_changelog(magisk["note"])
            await create_magisk(
                branch=m_type,
                version=magisk["version"],
                version_code=magisk["versionCode"],
                link=magisk["link"],
                note=magisk["note"],
                changelog=chg,
            )
            return await c.send_log_message(
                config.LOGS_ID,
                "<b>No data in the database.</b>\n"
                "<b>Saving Magisk data for the next sync...</b>\n"
                f"    <b>Magisk</b>: <code>{m_type}</code>\n\n"
                f"<b>Date</b>: <code>{date}</code>\n"
                "#Sync #Magisk #Releases",
            )
        if _magisk["version"] == magisk["version"] and int(
            _magisk["version_code"]
        ) == int(magisk["versionCode"]):
            return

        # do not send the Magisk Beta if it is the same version of Magisk Stable
        if m_type == "beta":
            r = await client.get(MAGISK_URL.format(m_type))
            data = r.json()
            magiskb = data["magisk"]
            _magisks = await get_magisk_by_branch(branch="stable")
            if magiskb["version"] == _magisks["version"] or int(
                magiskb["versionCode"]
            ) == int(_magisks["version_code"]):
                chg = await get_changelog(magisk["note"])
                await update_magisk_from_dict(
                    branch=m_type,
                    data={
                        "version": magisk["version"],
                        "version_code": int(magisk["versionCode"]),
                        "link": magisk["link"],
                        "note": magisk["note"],
                        "changelog": chg,
                    },
                )
                return

        file_name = f"Magisk{m_type.capitalize()}-{magisk['version']}_({magisk['versionCode']}).apk"
        file_path = DOWNLOAD_DIR + file_name
        async with aiodown.Client() as client:
            download = client.add(magisk["link"], file_path)
            await client.start()
            while not download.is_finished():
                await asyncio.sleep(0.5)
            if download.get_status() == "failed":
                return

        text = f"<b>Magisk {'v' if magisk['version'][0].isdecimal() else ''}{magisk['version']} ({magisk['versionCode']})</b>\n\n"
        text += f"⚡<i>Magisk {m_type.capitalize()}</i>\n"
        text += "⚡<i>Magisk is a suite of open source software for customizing Android, supporting devices higher than Android 5.0.</i>\n"
        text += (
            "⚡️<a href='https://github.com/topjohnwu/Magisk'>GitHub Repository</a>\n"
        )
        text += f"⚡<a href='{magisk['note']}'>Changelog</a>\n\n"
        text += "<b>By:</b> <a href='https://github.com/topjohnwu'>John Wu</a>\n"
        text += "<b>Follow:</b> @AndroidRepo"

        await c.send_channel_document(
            caption=text,
            document=file_path,
            parse_mode=ParseMode.DEFAULT,
            force_document=True,
        )
        os.remove(file_path)

    chg = await get_changelog(magisk["note"])
    await update_magisk_from_dict(
        branch=m_type,
        data={
            "version": magisk["version"],
            "version_code": int(magisk["versionCode"]),
            "link": magisk["link"],
            "note": magisk["note"],
            "changelog": chg,
        },
    )
    return await c.send_log_message(
        config.LOGS_ID,
        "<b>Magisk Releases check finished</b>\n"
        f"    <b>Updated</b>: <code>{m_type}</code>\n"
        f"    <b>Version</b>: <code>{magisk['version']} ({magisk['versionCode']})</code>\n\n"
        f"<b>Date</b>: <code>{date}</code>\n"
        "#Sync #Magisk #Releases",
    )
