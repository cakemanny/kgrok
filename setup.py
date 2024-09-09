from setuptools import setup

with open('./requirements.in') as f:
    dependencies = f.read().splitlines()

setup(
    install_requires=dependencies
)
