rm -rf dist build
python3 setup.py sdist bdist_wheel
python3 -m twine upload dist/*
rm -rf dist build *.egg-info
