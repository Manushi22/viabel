from distutils.core import setup

setup(
    name = 'viabel',
    version='0.2',
    description="Efficient, lightweight, variational inference approximation bounds",
    author='Jonathan H. Huggins',
    author_email='jhuggins@mit.edu',
    url='https://github.com/jhuggins/viabel/',
    packages=['viabel'],
    install_requires=['numpy'],
    extras_require={'vb' : ['scipy', 'autograd', 'tqdm', 'paragami'],
                    'examples' : ['scipy', 'autograd', 'tqdm', 'paragami',
                                  'matplotlib', 'seaborn', 'pandas', 'pystan']},
    python_requires='>=2.7',
    keywords = ['Bayesian inference',
                'variational inference',
                'Wasserstein distance',
                'alpha-divergence'],
    platforms='ALL',
)