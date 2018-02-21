from setuptools import setup

setup(name='graph_peak_caller',
      version='1.0.0',
      description='Graph peak caller',
      url='http://github.com/uio-bmi/graph_peak_caller',
      author='Ivar Grytten and Knut Rand',
      author_email='',
      license='MIT',
      packages=['graph_peak_caller'],
      zip_safe=False,
      dependency_links=['http://github.com/uio-cels/OffsetBasedGraph/tarball/v2.0#egg=package-1.0'],
      install_requires=['pymysql', 'numpy', 'filecache', 'scipy', 'pybedtools',
                        'memory_profiler', 'python-coveralls', 'matplotlib',
                        'biopython', 'pyfaidx'],
      classifiers=[
            'Programming Language :: Python :: 3'
      ],
      entry_points = {
        'console_scripts': ['graph_peak_caller=graph_peak_caller.command_line_interface:main'],
      }

      )
