# launcher.py
import sys
import os
from pathlib import Path

# Adiciona o diretório atual ao path para garantir os imports da src
sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == '__main__':
    import src.__main__
    # Forçar start da func main.
    src.__main__.main()
