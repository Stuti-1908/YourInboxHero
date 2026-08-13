import pathlib
def test_repo_structure():
    assert pathlib.Path('src').is_dir()
    assert pathlib.Path('requirements.txt').is_file()
    assert pathlib.Path('.github/workflows/ci.yml').is_file()
