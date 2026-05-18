#!/usr/bin/env fish
# Script nativo do Fish para executar o WaveControl CLI usando o ambiente virtual no macOS

# Garante que a execução aconteça no diretório correto, onde o script está localizado
set DIR (status dirname)
cd $DIR

# Executa o Python diretamente de dentro do ambiente virtual, repassando todos os argumentos ($argv)
exec ./.venv/bin/python main_cli.py $argv
