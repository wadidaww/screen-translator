from setuptools import find_packages, setup


setup(
    name="omniview-translator",
    version="0.1.0",
    description="Offline-first screen OCR translator",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[],
    entry_points={"console_scripts": ["omniview = src.app:main"]},
)
