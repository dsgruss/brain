cd doc
call make html
cd ..
mypy brain
pytest
black brain
black examples
flake8 brain
flake8 examples
cd examples
python setup.py build_ext --inplace
cd ..