# Datathon 7MLET - Grupo 80

## Visão Geral do Projeto

Este projeto foi desenvolvido para o Datathon da pós-graduação em Machine Learning Engineering.

O desafio consiste em criar uma solução de Machine Learning para apoiar decisões de ofertas e próximos passos em canais digitais, utilizando dados de clientes e histórico de campanhas.

## Problema de Negócio

Instituições financeiras realizam campanhas de marketing para oferecer produtos e serviços aos clientes. 

O objetivo deste projeto é desenvolver um modelo capaz de prever a probabilidade de conversão de um cliente, identificando quais clientes possuem maior chance de aceitar uma oferta.

## Objetivo do Projeto

O projeto tem como objetivo:

- Realizar análise exploratória dos dados;
- Preparar a base para modelos de Machine Learning;
- Desenvolver um modelo preditivo de conversão;
- Criar uma solução que possa apoiar experimentações de ofertas e mensagens.

## Base de Dados

Foi utilizada a base pública:

Bank Marketing Dataset

Link Kaggle:
https://www.kaggle.com/datasets/henriqueyamahata/bank-marketing

A variável alvo utilizada é:

- `yes`: cliente aceitou a oferta;
- `no`: cliente não aceitou a oferta.

## Estrutura do Projeto

```
datathon-7mlet-grupo-XX/

├── data/
│   ├── raw/
│   │   └── bank-additional-full.csv
│   │
│   └── processed/

├── notebooks/
│   └── 01_eda.ipynb

├── src/

├── README.md

└── requirements.txt
```

## Como Executar

Clone o repositório:

```bash
git clone https://github.com/VehGarciiah/datathon-7mlet-grupo-80
```

Instale as dependências:

```bash
pip install -r requirements.txt
```

Execute o notebook de análise:

```bash
jupyter notebook
```