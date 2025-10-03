# PyInstaller hook para MediaPipe
# Garante que todos os modelos e arquivos binários sejam incluídos

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Coletar todos os arquivos de dados do MediaPipe
datas = collect_data_files('mediapipe', include_py_files=False)

# Coletar todos os submódulos
hiddenimports = collect_submodules('mediapipe')

# Adicionar imports específicos importantes
hiddenimports += [
    'mediapipe.calculators',
    'mediapipe.framework',
    'mediapipe.framework.formats',
    'mediapipe.modules',
    'mediapipe.python',
    'mediapipe.python._framework_bindings',
    'mediapipe.python.solutions',
    'mediapipe.python.solutions.hands',
    'mediapipe.python.solutions.drawing_utils',
    'mediapipe.python.solutions.drawing_styles',
    'mediapipe.tasks',
    'mediapipe.tasks.python',
]

