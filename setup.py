from setuptools import setup
from os import path, walk
import sys

DATA_FILES = []

def include_documentation(local_dir, install_dir):
    global DATA_FILES
    if 'bdist_wheel' in sys.argv and not path.exists(local_dir):
        print(f"Directory '{path.abspath(local_dir)}' does not exist. "
              f"Please build documentation before running bdist_wheel.")
        sys.exit(0)

    for dirpath, _, files in walk(local_dir):
        target_dir = dirpath.replace(local_dir, install_dir)
        full_paths = [path.join(dirpath, f) for f in files]
        DATA_FILES.append((target_dir, full_paths))

include_documentation('doc/_build/html', 'help/orange3-example')

setup(
    data_files=DATA_FILES,
)
