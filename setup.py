from setuptools import setup, find_packages

setup(
    name="auto-bot-sber",
    version="0.1",
    packages=find_packages(),
    install_requires=[
        "aiohttp==3.11.18",
        "python-dotenv==1.0.1",
    ],
) 