from setuptools import setup, find_packages

setup(
    name="pdf_annotation_tool",
    version="1.0",
    packages=find_packages(),
    install_requires=[
        "PyMuPDF",
        "requests",
        "PyQt5",
        "Pillow",
        "langchain",
        "langchain-openai",
        "unstructured",
        "shapely"
    ],
    entry_points={
        "gui_scripts": [
            "pdf_annotation_tool=main:main",
        ],
    },
)
