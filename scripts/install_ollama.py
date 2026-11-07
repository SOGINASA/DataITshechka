"""Install a pinned official portable Ollama build into this workspace."""
import hashlib
from pathlib import Path
import shutil
from urllib.request import urlopen
from zipfile import ZipFile

VERSION = 'v0.40.15'
SHA256 = '9ca74a7ab66ec86870b1eecac7df160df08dc4e3a291ab5d2d59bcf9310221c6'
URL = f'https://github.com/ollama/ollama/releases/download/{VERSION}/ollama-windows-amd64.zip'
ROOT = Path(__file__).resolve().parents[1] / '.tools'


def main():
    ROOT.mkdir(exist_ok=True)
    archive = ROOT / f'ollama-{VERSION}.zip'
    target = ROOT / 'ollama'
    installed_hash = None
    if archive.exists():
        with archive.open('rb') as source:
            installed_hash = hashlib.file_digest(source, 'sha256').hexdigest()
    if installed_hash != SHA256:
        free = shutil.disk_usage(ROOT).free
        if free < 9 * 1024**3:
            raise SystemExit('At least 9 GiB free space required for runtime and model.')
        part = archive.with_suffix('.part')
        count, next_report = 0, 0
        with urlopen(URL, timeout=60) as response, part.open('wb') as output:
            while chunk := response.read(4 * 1024**2):
                output.write(chunk)
                count += len(chunk)
                if count >= next_report:
                    print(f'Downloaded {count // 1024**2} MiB', flush=True)
                    next_report = count + 128 * 1024**2
        with part.open('rb') as source:
            if hashlib.file_digest(source, 'sha256').hexdigest() != SHA256:
                raise SystemExit('Official release SHA256 mismatch; archive not extracted.')
        part.replace(archive)
    with ZipFile(archive) as package:
        for entry in package.infolist():
            if not (target / entry.filename).resolve().is_relative_to(target.resolve()):
                raise SystemExit('Unsafe archive path')
        package.extractall(target)
    print(f'Installed Ollama {VERSION}: {target / "ollama.exe"}', flush=True)


if __name__ == '__main__':
    main()
