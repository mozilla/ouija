from setuptools import setup, find_packages


required = [
    "Flask",
    "MarkupSafe",
    "MySQL-python",
    "argparse",
    "requests"
]

setup(
    name='ouija',
    packages=find_packages(),
    install_requires=required + ['pytest-runner'],
    tests_require=required + ['mock', 'pytest'],
    license='MPL',
    url='https://github.com/dminor/ouija',
)
