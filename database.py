import sqlite3
import os

DB_FILE = "tarefas.db"

if os.path.exists(DB_FILE):
    os.remove(DB_FILE)
    print("Banco de dados antigo removido para a V4.0 (Hábitos)!")

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# --- TABELAS EXISTENTES (V1.0 e V2.0) ---
# Tabela de Categorias
cursor.execute("""
CREATE TABLE IF NOT EXISTS Categorias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE, icone TEXT, cor TEXT DEFAULT '#cccccc'
);
""")
# Tabela de Tarefas
cursor.execute("""
CREATE TABLE IF NOT EXISTS Tarefas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL, descricao TEXT,
    data_criacao DATETIME DEFAULT (STRFTIME('%Y-%m-%d %H:%M:%S', 'now', 'localtime')),
    data_vencimento DATE, status TEXT DEFAULT 'Pendente', recorrencia TEXT DEFAULT 'Única',
    categoria_id INTEGER, ultima_geracao DATE,
    data_conclusao DATETIME, concluida_no_prazo INTEGER,
    FOREIGN KEY(categoria_id) REFERENCES Categorias(id)
);
""")
# Tabela de Avisos
cursor.execute("""
CREATE TABLE IF NOT EXISTS Avisos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    descricao TEXT NOT NULL, prioridade TEXT NOT NULL,
    data_inicio DATE NOT NULL, data_fim DATE NOT NULL,
    data_criacao DATETIME DEFAULT (STRFTIME('%Y-%m-%d %H:%M:%S', 'now', 'localtime'))
);
""")
# Tabela de Treinos
cursor.execute("""
CREATE TABLE IF NOT EXISTS Treinos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE,
    descricao TEXT
);
""")
# Tabela de Exercícios
cursor.execute("""
CREATE TABLE IF NOT EXISTS Exercicios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL, series TEXT,
    carga_atual REAL DEFAULT 0, observacao TEXT,
    treino_id INTEGER NOT NULL,
    FOREIGN KEY(treino_id) REFERENCES Treinos(id) ON DELETE CASCADE
);
""")
# Tabela de Sessões de Treino
cursor.execute("""
CREATE TABLE IF NOT EXISTS TreinoSessoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    treino_id INTEGER NOT NULL,
    data_sessao DATETIME DEFAULT (STRFTIME('%Y-%m-%d %H:%M:%S', 'now', 'localtime')),
    observacoes TEXT,
    FOREIGN KEY(treino_id) REFERENCES Treinos(id) ON DELETE CASCADE
);
""")
# Tabela de Logs de Exercícios
cursor.execute("""
CREATE TABLE IF NOT EXISTS ExercicioLogs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sessao_id INTEGER NOT NULL, exercicio_id INTEGER NOT NULL,
    serie INTEGER NOT NULL, carga REAL NOT NULL, reps INTEGER NOT NULL,
    FOREIGN KEY(sessao_id) REFERENCES TreinoSessoes(id) ON DELETE CASCADE,
    FOREIGN KEY(exercicio_id) REFERENCES Exercicios(id) ON DELETE CASCADE
);
""")
print("Tabelas antigas criadas com sucesso.")

# --- TABELAS DO MÓDULO DE HÁBITOS (V4.0) ---
cursor.execute("""
CREATE TABLE IF NOT EXISTS Habitos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE,
    ativo INTEGER DEFAULT 1, -- 1 para ativo, 0 para inativo
    data_criacao DATETIME DEFAULT (STRFTIME('%Y-%m-%d %H:%M:%S', 'now', 'localtime'))
);
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS HabitoLogs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    habito_id INTEGER NOT NULL,
    data_conclusao DATE NOT NULL,
    FOREIGN KEY(habito_id) REFERENCES Habitos(id) ON DELETE CASCADE,
    -- Garante que um hábito não pode ser concluído duas vezes no mesmo dia
    UNIQUE(habito_id, data_conclusao) 
);
""")
print("Tabelas de Hábitos (V4.0) criadas com sucesso.")


# --- DADOS INICIAIS ---
print("Inserindo dados iniciais...")
# Categorias e Treinos
categorias_iniciais = [('Saúde', 'fa-heart-pulse', '#20a8d8'), ('Cuidados Pessoais', 'fa-spa', '#f86c6b'), ('Casa', 'fa-home', '#ffc107'), ('Lions Techs', 'fa-paw', '#4dbd74'), ('Fogo3D', 'fa-fire', '#fd7e14'), ('Projetos Novos', 'fa-lightbulb', '#6f42c1'), ('Trabalho', 'fa-briefcase', '#63c2de'), ('Estudos', 'fa-book', '#c8ced3'), ('Veículos', 'fa-car', '#c8ced3'), ('Pessoal', 'fa-user', '#6f42c1'), ('Eventos', 'fa-calendar', '#20a8d8'), ('Lazer', 'fa-gamepad', '#f86c6b')]
cursor.executemany("INSERT INTO Categorias (nome, icone, cor) VALUES (?, ?, ?);", categorias_iniciais)
treinos_iniciais = [('Treino A', 'Peito e Tríceps'), ('Treino B', 'Costas e Bíceps'), ('Treino C', 'Pernas e Ombros'), ('Treino D', 'Abdômen e Core')]
cursor.executemany("INSERT INTO Treinos (nome, descricao) VALUES (?, ?);", treinos_iniciais)

# Inserindo hábitos padrão para começar
habitos_iniciais = [
    ("Ler 10 páginas",),
    ("Meditar",),
    ("Beber 3L de água",),
]
cursor.executemany("INSERT INTO Habitos (nome) VALUES (?);", habitos_iniciais)
print("Dados iniciais de Categorias, Treinos e Hábitos inseridos.")

conn.commit()
conn.close()
print("\nBanco de dados V4.0 (com módulo de hábitos) criado e configurado com sucesso!")