# Guia do pessoal

Lousa de planejamento de decoração de Natal com acesso por e-mail e senha. As ideias e usuários ficam em SQLite local ou PostgreSQL em produção.

## Desenvolvimento local

No PowerShell, nesta pasta:

```powershell
..\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

Deixe `DATABASE_URL` vazio para usar o SQLite local. Para `APP_SECRET_KEY`, gere um valor com `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Salve o `.env` e inicie:

```powershell
python app.py
```

Crie contas autorizadas pelo terminal; não existe cadastro público:

```powershell
python manage_users.py add pessoa@exemplo.com
```

A senha é solicitada sem aparecer na tela e guardada como hash. Para criar uma conta administradora, use `python manage_users.py add-admin pessoa@exemplo.com`. Para listar ou alterar contas pelo terminal, use `python manage_users.py list`, `disable email@exemplo.com`, `enable email@exemplo.com` e `reset-password email@exemplo.com`. Administradores também podem criar contas pela tela **Usuários** do painel. Redefinir a senha ou desativar a conta invalida as sessões existentes. Depois de entrar, qualquer usuário pode alterar sua senha no menu da conta.

As tentativas de senha são limitadas por combinação de e-mail e endereço de origem (no Vercel, pelo `X-Forwarded-For`, reescrito pela plataforma). Requisições e textos da lousa têm limites de tamanho.

Administradores podem abrir **Atividade** no painel para consultar as 200 ações mais recentes da lousa. O sistema registra quem adicionou uma ideia, mudou seu status ou a removeu, além do IP de origem da requisição; cada registro é salvo junto com a alteração no PostgreSQL/SQLite e só pode ser consultado por administradores.

O painel, o login, a troca de senha e a administração de usuários oferecem modo claro e escuro. A escolha fica salva no navegador; sem uma escolha anterior, é usada a preferência de aparência do sistema.

## Preparar para Vercel

O Flask é detectado pelo Vercel e a aplicação é atendida por uma função Python. `vercel.json` posiciona a função em São Paulo (`gru1`), perto dos usuários. Para reduzir a latência do banco, escolha também uma região de banco próxima, como São Paulo (`sa-east-1`) no Supabase.

1. Conecte esta pasta a um projeto Vercel pelo Git ou CLI e associe o projeto ao diretório `Guia-do-pessoal`. O Flask é reconhecido pelo `app.py` e `requirements.txt`. Os assets de navegador ficam em `public/` para serem servidos pelo CDN do Vercel; `.vercelignore` e `functions.app.py.excludeFiles` removem ambiente virtual, banco local, chave local e arquivos de gestão do bundle.
2. Provisione um PostgreSQL pelo Marketplace do Vercel. No Supabase, escolha a região São Paulo. Use a connection string pooled do provedor como `DATABASE_URL` no Vercel e, temporariamente, no `.env` local.
3. Copie o `natal.db` local para o Postgres:

   ```powershell
   python migrate_to_postgres.py
   ```

   O comando copia ideias e contas existentes. Se ainda não tiver usuários, não há contas para copiar; crie-as com `manage_users.py add` enquanto `DATABASE_URL` aponta para o Postgres.
4. Configure no projeto Vercel as variáveis `DATABASE_URL`, `APP_SECRET_KEY` e `COOKIE_SECURE=1`. Gere um `APP_SECRET_KEY` novo para produção; não reutilize nem publique a chave local. Marque chaves e URLs de banco como valores sensíveis no painel.
5. Faça o primeiro deploy e confirme que a tela de login abre e que usuários cadastrados conseguem entrar com e-mail e senha.

O esquema é criado de forma idempotente na primeira requisição da aplicação. O pool PostgreSQL é global por instância e limitado por `DB_POOL_MAX` (padrão 3), evitando abrir conexões ilimitadas sob concorrência. O valor pode ser reduzido se o provedor tiver um limite baixo de conexões. O projeto usa `gru1` para aproximar a função do público brasileiro; o banco também deve ficar em São Paulo para manter a conexão curta.

Não faça commit de `.env`, `natal.db` nem `.app_secret_key`; eles já estão no `.gitignore`.
