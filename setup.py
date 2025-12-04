from setuptools import setup

if __name__ == "__main__":
    setup(
        name="mgit",
        setup_requires="setupmeta",
        versioning="dev",
        author="Zoran Simic zoran@simicweb.com",
        url="https://github.com/zsimic/mgit",
        entry_points={
            "console_scripts": [
                "mgit = mgit.cli:main",
            ],
        },
        python_requires=">=3.10",
        classifiers=[
            "Development Status :: 4 - Beta",
            "Environment :: Console",
            "Intended Audience :: Developers",
            "Operating System :: MacOS :: MacOS X",
            "Operating System :: POSIX",
            "Operating System :: Unix",
            "Programming Language :: Python",
            "Programming Language :: Python :: 3",
            "Programming Language :: Python :: 3.10",
            "Programming Language :: Python :: 3.11",
            "Programming Language :: Python :: 3.12",
            "Programming Language :: Python :: 3.13",
            "Programming Language :: Python :: 3.14",
            "Programming Language :: Python :: Implementation :: CPython",
            "Topic :: Software Development :: Build Tools",
            "Topic :: Utilities"
        ],
    )
