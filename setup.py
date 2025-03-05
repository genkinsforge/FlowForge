import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="flowforge",
    version="0.1.0",
    author="Genkins Forge LLC",
    author_email="info@genkinsforge.com",
    description="A robust converter from Draw.io diagrams to Mermaid diagrams.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/genkinsforge/FlowForge",
    packages=setuptools.find_packages(),  # This will find the "flowforge" package
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)

