import os
import codecs
from setuptools import setup

here = os.path.abspath(os.path.dirname(__file__))
with codecs.open(os.path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='nest_asyncio',
    version='0.9.6',
    description='Patch asyncio to allow nested event loops',
    long_description=long_description,
    url='https://github.com/erdewit/nest_asyncio',
    author='Ewald R. de Wit',
    author_email='ewald.de.wit@gmail.com',
    license='BSD',
    python_requires='>=3.5',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3 :: Only',
    ],
    keywords='asyncio nested eventloop',
    py_modules=['nest_asyncio']
)
