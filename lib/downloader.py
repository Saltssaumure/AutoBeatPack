"""
Parallel download utils
"""

import asyncio
import os
from urllib import parse

import aiohttp

from lib.error import DownloadError
from lib.pretty import ind, pprint, q, size, time
from lib.disk import OpenModes

__all__ = ["download_batch", "download_decision", "download_file"]


async def download_file(abs_filename: str, response: str, expected_size: int, mode: OpenModes, filesize: int = 0):
    """Download file and report progress"""

    filename = os.path.basename(abs_filename)

    with open(abs_filename, mode=mode.value) as file:  # pylint: disable=unspecified-encoding
        old_prog = 0
        # Get and write chunks of 1024 bytes
        # Print progress every 1%
        chunk_size = 1024
        increment = 10
        while True:
            chunk = await response.content.read(chunk_size)
            if not chunk:
                break
            file.write(chunk)
            filesize += chunk_size
            percent = filesize * 100 / expected_size
            new_prog = int(percent / increment)
            if new_prog > old_prog:
                old_prog = new_prog
                pprint(ind(f"{q(filename)} - {percent:.0f}%"))
    pprint(f"{ind(f'Downloaded {q(filename)}!')}")


async def download_decision(url: str, abs_download_folder: str):
    """Decide whether to download file from url based on local file contents."""
    filename = os.path.basename(parse.unquote(parse.urlparse(url).path))
    abs_filename = os.path.join(abs_download_folder, filename)

    filesize = os.path.getsize(abs_filename) if os.path.exists(abs_filename) else 0

    if not os.path.exists(abs_download_folder):
        os.makedirs(abs_download_folder)

    # Get expected size of whole file
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                expected_size = int(response.headers["Content-Length"])
    except KeyError as exc:
        raise DownloadError(f"Could not get size of {q(filename)} from {q(url)}") from exc

    # Decide whether to download file
    async with aiohttp.ClientSession(headers={"Range": f"bytes={filesize}-"}) as session:
        async with session.get(url) as response:
            p_starting = ind(f"Starting {q(filename)} ({await size(expected_size)})")
            p_skipped = ind(f"Skipped {q(filename)} (match)")
            p_resuming = ind(
                f"Resuming {q(filename)} ({await size(filesize)} of {await size(expected_size)})"
            )

            if not os.path.exists(abs_filename):
                pprint(p_starting)
                await download_file(abs_filename, response, expected_size, OpenModes.WRITE_BYTE)
            elif filesize == 0:
                pprint(p_starting)
                await download_file(abs_filename, response, expected_size, OpenModes.OVERWRITE_BYTE)
            elif filesize >= expected_size:
                pprint(p_skipped)
            else:
                pprint(p_resuming)
                await download_file(
                    abs_filename, response, expected_size, OpenModes.APPEND_BYTE, filesize=filesize
                )


async def download_batch(batch: int, urls: list[str], abs_download_folder: str):
    """Download files in current batch in parallel"""
    pprint(f"Batch {batch} - {time()}")
    tasks = [download_decision(url, abs_download_folder) for url in urls]
    await asyncio.gather(*tasks)
