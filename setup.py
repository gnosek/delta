from setuptools import setup

setup(
    name='delta',
    version='0.1',
    py_modules=['delta'],
    install_requires=[
        'Click',
        'ansicolors',
    ],
    entry_points='''
        [console_scripts]
        delta=delta:cli
    ''',
)
