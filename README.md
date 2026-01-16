# Gerador de Horário Escolar

Este é um projeto para gerar horários escolares de forma otimizada utilizando Streamlit e OR-Tools.

## Funcionalidades
- **Login Seguro**: Sistema de autenticação com suporte a JWT.
- **Upload de Dados**: Suporte para planilhas Excel com informações de turmas e professores.
- **Geração de Horários**: Utiliza o Google OR-Tools para otimizar a distribuição de aulas.
- **Relatórios**: Geração de PDFs com os horários finais.

## Requisitos
- Python 3.12+
- Dependências listadas em `requirements.txt`

## Como Executar
1. Clone o repositório:
   ```bash
   git clone https://github.com/seu-usuario/seu-repositorio.git
   ```
2. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
3. Execute o aplicativo:
   ```bash
   streamlit run app.py
   ```

## Configuração
- **Credenciais**: Configure o arquivo `secrets.toml` com os usuários e senhas.
- **Hospedagem**: Para produção, hospede o projeto no [Streamlit Cloud](https://streamlit.io/cloud) ou outro serviço de sua escolha.

## Licença
Este projeto está licenciado sob a [MIT License](LICENSE).