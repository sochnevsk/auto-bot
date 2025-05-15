from setuptools import setup, find_packages

setup(
    name="auto-bot",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "python-telegram-bot",
        "python-dotenv",
        "pydantic",
        "pydantic-settings",
    ],
) 