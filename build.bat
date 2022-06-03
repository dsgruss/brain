cd doc
call make html
cd ..
mypy brain
pytest
black brain
black examples
flake8 brain
flake8 examples