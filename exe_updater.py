# Standalone updater EXE, separate from the application directory.
import argparse
import ctypes
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

def wait_exit(pid):
    if os.name != 'nt':
        return
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x00100000, False, pid)
    if h:
        try:
            if k.WaitForSingleObject(h, 60000) == 0x102:
                raise TimeoutError('기존 프로그램이 종료되지 않았습니다')
        finally:
            k.CloseHandle(h)

def update(archive, folder):
    folder = Path(folder).resolve()
    root = folder.parent
    backup = root / '_previous_version'
    staged = Path(tempfile.mkdtemp(prefix='siaaebi_stage_', dir=str(root)))
    try:
        with zipfile.ZipFile(archive) as z:
            members = z.infolist()
            if not any(m.filename == 'SiaAebiBlogWriter.exe' for m in members):
                raise ValueError('실행 파일이 없습니다')
            for m in members:
                n = m.filename.replace('\\', '/')
                parts = Path(n).parts
                if n.startswith('/') or '..' in parts or ':' in n or m.file_size > 250_000_000:
                    raise ValueError('잘못된 업데이트 파일 경로')
                if m.is_dir():
                    continue
                target = staged.joinpath(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(m) as f, target.open('wb') as out:
                    shutil.copyfileobj(f, out)
        if backup.exists():
            shutil.rmtree(backup)
        folder.rename(backup)
        try:
            staged.rename(folder)
        except Exception:
            backup.rename(folder)
            raise
    finally:
        if staged.exists():
            shutil.rmtree(staged)
    return folder

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--archive', required=True)
    p.add_argument('--folder', required=True)
    p.add_argument('--pid', required=True, type=int)
    a = p.parse_args()
    root = Path(a.folder).resolve().parent
    log = root / 'update_log.txt'
    try:
        wait_exit(a.pid)
        folder = update(a.archive, a.folder)
        subprocess.Popen([str(folder / 'SiaAebiBlogWriter.exe')], cwd=str(folder))
        log.write_text('업데이트 성공', encoding='utf-8')
    except Exception as e:
        log.write_text('업데이트 실패: ' + repr(e), encoding='utf-8')
        old = Path(a.folder) / 'SiaAebiBlogWriter.exe'
        if old.exists():
            try:
                subprocess.Popen([str(old)], cwd=str(old.parent))
            except Exception:
                pass

if __name__ == '__main__':
    main()
