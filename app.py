import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from datetime import date, datetime, timedelta
import pytz
from collections import defaultdict

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_super_dificil'
DATABASE = 'tarefas.db'
SAO_PAULO_TZ = pytz.timezone('America/Sao_Paulo')

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def get_hoje():
    return datetime.now(SAO_PAULO_TZ).date()

def get_agora():
    return datetime.now(SAO_PAULO_TZ)

def atualizar_status_tarefas_vencidas(conn):
    hoje_str = str(get_hoje())
    cursor = conn.cursor()
    cursor.execute("UPDATE Tarefas SET status = 'Não Concluída' WHERE data_vencimento < ? AND status = 'Pendente';", (hoje_str,))

def gerar_tarefas_recorrentes(conn):
    cursor = conn.cursor()
    hoje = get_hoje()
    tarefas_recorrentes_mae = cursor.execute("SELECT * FROM Tarefas WHERE recorrencia != 'Única'").fetchall()
    for tarefa_mae_row in tarefas_recorrentes_mae:
        tarefa_mae = dict(tarefa_mae_row)
        if not tarefa_mae['ultima_geracao']: continue
        ultima_geracao_data = datetime.strptime(tarefa_mae['ultima_geracao'], '%Y-%m-%d').date()
        proxima_data = ultima_geracao_data
        while proxima_data < hoje:
            if tarefa_mae['recorrencia'] == 'Diária': proxima_data += timedelta(days=1)
            elif tarefa_mae['recorrencia'] == 'Semanal': proxima_data += timedelta(weeks=1)
            elif tarefa_mae['recorrencia'] == 'Mensal':
                ano, mes = proxima_data.year, proxima_data.month; mes += 1
                if mes > 12: mes = 1; ano += 1
                proxima_data = proxima_data.replace(year=ano, month=mes)
            elif tarefa_mae['recorrencia'] == 'Anual': proxima_data = proxima_data.replace(year=proxima_data.year + 1)
            if proxima_data <= hoje:
                cursor.execute("INSERT INTO Tarefas (titulo, descricao, categoria_id, recorrencia, data_vencimento) VALUES (?, ?, ?, 'Única', ?)",(tarefa_mae['titulo'], tarefa_mae['descricao'], tarefa_mae['categoria_id'], proxima_data.strftime('%Y-%m-%d')))
                ultima_geracao_data = proxima_data
        cursor.execute("UPDATE Tarefas SET ultima_geracao = ? WHERE id = ?", (ultima_geracao_data.strftime('%Y-%m-%d'), tarefa_mae['id']))

@app.route("/")
def index():
    conn = get_db_connection()
    atualizar_status_tarefas_vencidas(conn)
    gerar_tarefas_recorrentes(conn)
    conn.commit()
    
    hoje = get_hoje()
    hoje_str = str(hoje)
    
    avisos = conn.execute("SELECT * FROM Avisos WHERE ? BETWEEN data_inicio AND data_fim ORDER BY CASE prioridade WHEN 'Emergencial' THEN 1 WHEN 'Alta' THEN 2 WHEN 'Média' THEN 3 WHEN 'Baixa' THEN 4 ELSE 5 END;", (hoje_str,)).fetchall()
    todas_as_tarefas_pendentes = conn.execute("SELECT t.*, c.nome as categoria_nome, c.icone as categoria_icone, c.cor as categoria_cor FROM Tarefas t LEFT JOIN Categorias c ON t.categoria_id = c.id WHERE t.status = 'Pendente' ORDER BY t.data_vencimento;").fetchall()
    tarefas_hoje, tarefas_outras = [], []
    for tarefa_row in todas_as_tarefas_pendentes:
        tarefa = dict(tarefa_row)
        tarefa['is_atrasada'] = False
        if tarefa['data_vencimento'] and tarefa['data_vencimento'] < hoje_str: tarefa['is_atrasada'] = True
        if tarefa['data_vencimento'] == hoje_str or (tarefa['recorrencia'] == 'Diária' and tarefa['ultima_geracao'] is not None and not tarefa['is_atrasada']):
            tarefas_hoje.append(tarefa)
        else:
            tarefas_outras.append(tarefa)
    tarefas_por_categoria = {}
    for tarefa in tarefas_outras:
        categoria = tarefa['categoria_nome'] or 'Sem Categoria'
        if categoria not in tarefas_por_categoria: tarefas_por_categoria[categoria] = []
        tarefas_por_categoria[categoria].append(tarefa)
        
    kpis = {
        'total': conn.execute('SELECT COUNT(id) as count FROM Tarefas;').fetchone()['count'],
        'pendentes': conn.execute("SELECT COUNT(id) as count FROM Tarefas WHERE status = 'Pendente';").fetchone()['count'],
        'concluidas': conn.execute("SELECT COUNT(id) as count FROM Tarefas WHERE status = 'Concluída';").fetchone()['count'],
        'nao_concluidas': conn.execute("SELECT COUNT(id) as count FROM Tarefas WHERE status = 'Não Concluída';").fetchone()['count']
    }
    
    total_finalizadas = kpis['concluidas'] + kpis['nao_concluidas']
    if total_finalizadas > 0:
        kpis['perc_tarefas_concluidas'] = (kpis['concluidas'] * 100.0) / total_finalizadas
    else: kpis['perc_tarefas_concluidas'] = 0
    
    inicio_da_semana = hoje - timedelta(days=hoje.weekday())
    fim_da_semana = inicio_da_semana + timedelta(days=6)
    
    sessoes_na_semana = conn.execute("SELECT COUNT(id) as count FROM TreinoSessoes WHERE date(data_sessao) BETWEEN ? AND ?", (inicio_da_semana.strftime('%Y-%m-%d'), fim_da_semana.strftime('%Y-%m-%d'))).fetchone()['count']
    META_TREINOS_SEMANAL = 5
    if META_TREINOS_SEMANAL > 0:
        kpis['perc_treinos_semana'] = (sessoes_na_semana * 100.0) / META_TREINOS_SEMANAL
    else:
        kpis['perc_treinos_semana'] = 0

    habitos_ativos = conn.execute("SELECT COUNT(id) as count FROM Habitos WHERE ativo = 1").fetchone()['count']
    if habitos_ativos > 0:
        oportunidades_habitos = habitos_ativos * (hoje.weekday() + 1)
        if oportunidades_habitos > 0:
            sucessos_habitos = conn.execute("SELECT COUNT(id) as count FROM HabitoLogs WHERE data_conclusao BETWEEN ? AND ?", (inicio_da_semana.strftime('%Y-%m-%d'), hoje_str)).fetchone()['count']
            kpis['perc_habitos_semana'] = (sucessos_habitos * 100.0) / oportunidades_habitos
        else:
            kpis['perc_habitos_semana'] = 0
    else:
        kpis['perc_habitos_semana'] = 0

    tarefas_concluidas = conn.execute("SELECT t.id, t.titulo, c.nome as categoria_nome FROM Tarefas t LEFT JOIN Categorias c ON t.categoria_id = c.id WHERE t.status = 'Concluída' ORDER BY t.data_conclusao DESC LIMIT 5;").fetchall()
    tarefas_nao_concluidas = conn.execute("SELECT t.titulo, c.nome as categoria_nome, t.data_vencimento FROM Tarefas t LEFT JOIN Categorias c ON t.categoria_id = c.id WHERE t.status = 'Não Concluída' ORDER BY t.data_vencimento DESC LIMIT 5;").fetchall()
    previsao_recorrentes = []
    tarefas_recorrentes_mae = conn.execute("SELECT t.*, c.nome as categoria_nome FROM Tarefas t LEFT JOIN Categorias c ON t.categoria_id = c.id WHERE t.recorrencia != 'Única'").fetchall()
    for tarefa_mae in tarefas_recorrentes_mae:
        if tarefa_mae['ultima_geracao']:
            proxima_data = datetime.strptime(tarefa_mae['ultima_geracao'], '%Y-%m-%d').date()
            if tarefa_mae['recorrencia'] == 'Diária': proxima_data += timedelta(days=1)
            elif tarefa_mae['recorrencia'] == 'Semanal': proxima_data += timedelta(weeks=1)
            elif tarefa_mae['recorrencia'] == 'Mensal':
                ano, mes = proxima_data.year, proxima_data.month; mes += 1
                if mes > 12: mes = 1; ano += 1
                proxima_data = proxima_data.replace(year=ano, month=mes)
            elif tarefa_mae['recorrencia'] == 'Anual': proxima_data = proxima_data.replace(year=proxima_data.year + 1)
            if proxima_data > hoje:
                previsao_recorrentes.append({"titulo": tarefa_mae['titulo'],"categoria_nome": tarefa_mae['categoria_nome'],"data_vencimento_futura": proxima_data})
    dados_grafico_raw = conn.execute("SELECT COALESCE(c.nome, 'Sem Categoria') as categoria, COALESCE(c.cor, '#868e96') as cor, COUNT(t.id) as contagem FROM Tarefas t LEFT JOIN Categorias c ON t.categoria_id = c.id WHERE t.status = 'Concluída' GROUP BY categoria, cor ORDER BY contagem DESC;").fetchall()
    grafico_labels = [row['categoria'] for row in dados_grafico_raw]
    grafico_data = [row['contagem'] for row in dados_grafico_raw]
    grafico_cores = [row['cor'] for row in dados_grafico_raw]
    dados_grafico = {"labels": grafico_labels, "data": grafico_data, "cores": grafico_cores}
    dias_da_semana = [inicio_da_semana + timedelta(days=i) for i in range(7)]
    habitos = conn.execute("SELECT * FROM Habitos WHERE ativo = 1 ORDER BY nome").fetchall()
    logs = conn.execute("SELECT habito_id, data_conclusao FROM HabitoLogs WHERE data_conclusao BETWEEN ? AND ?", (inicio_da_semana.strftime('%Y-%m-%d'), fim_da_semana.strftime('%Y-%m-%d'))).fetchall()
    logs_da_semana = {(log['habito_id'], log['data_conclusao']) for log in logs}
    habitos_com_status = []
    for habito in habitos:
        status_semana = {}
        for dia in dias_da_semana:
            status_semana[dia.strftime('%Y-%m-%d')] = (habito['id'], dia.strftime('%Y-%m-%d')) in logs_da_semana
        habitos_com_status.append({'id': habito['id'], 'nome': habito['nome'], 'status_semana': status_semana})
    
    # LÓGICA DE EVOLUÇÃO DE TREINO AGORA ESTÁ AQUI
    evolucao_treinos = []
    inicio_semana_passada = inicio_da_semana - timedelta(days=7)
    fim_semana_passada = inicio_da_semana - timedelta(days=1)
    volumes_sessoes = conn.execute("SELECT s.id, s.treino_id, t.nome as treino_nome, date(s.data_sessao) as data, SUM(l.carga * l.reps) as volume_total FROM TreinoSessoes s JOIN ExercicioLogs l ON l.sessao_id = s.id JOIN Treinos t ON s.treino_id = t.id WHERE date(s.data_sessao) BETWEEN ? AND ? GROUP BY s.id, s.treino_id, t.nome, data", (inicio_semana_passada.strftime('%Y-%m-%d'), fim_da_semana.strftime('%Y-%m-%d'))).fetchall()
    vol_semana_passada = defaultdict(list); vol_semana_atual = defaultdict(list)
    for sessao in volumes_sessoes:
        data_sessao = datetime.strptime(sessao['data'], '%Y-%m-%d').date()
        if inicio_semana_passada <= data_sessao <= fim_semana_passada:
            vol_semana_passada[sessao['treino_nome']].append(sessao['volume_total'])
        elif inicio_da_semana <= data_sessao <= fim_da_semana:
            vol_semana_atual[sessao['treino_nome']].append(sessao['volume_total'])
    for nome_treino, volumes in vol_semana_atual.items():
        if nome_treino in vol_semana_passada:
            avg_atual = sum(volumes) / len(volumes)
            avg_passado = sum(vol_semana_passada[nome_treino]) / len(vol_semana_passada[nome_treino])
            if avg_passado > 0:
                evolucao = ((avg_atual - avg_passado) / avg_passado) * 100
                evolucao_treinos.append({'nome': nome_treino, 'evolucao': evolucao})

    conn.close()
    
    return render_template(
        'index.html', avisos=avisos, tarefas_hoje=tarefas_hoje,
        tarefas_por_categoria=tarefas_por_categoria, kpis=kpis,
        tarefas_concluidas=tarefas_concluidas, tarefas_nao_concluidas=tarefas_nao_concluidas,
        previsao_recorrentes=previsao_recorrentes, dados_grafico=dados_grafico,
        habitos=habitos_com_status, dias_da_semana=dias_da_semana,
        evolucao_treinos=evolucao_treinos
    )


@app.route('/nova_tarefa')
def nova_tarefa_page():
    conn = get_db_connection()
    categorias = conn.execute('SELECT * FROM Categorias ORDER BY nome;').fetchall()
    conn.close()
    return render_template('nova_tarefa.html', categorias=categorias)

@app.route("/add", methods=['POST'])
def add_task():
    titulo = request.form['titulo']; categoria_id = request.form['categoria_id']; data_vencimento = request.form['data_vencimento'] or None; recorrencia = request.form['recorrencia']; descricao = request.form['descricao']
    ultima_geracao = None
    if recorrencia != 'Única': ultima_geracao = data_vencimento
    if titulo:
        conn = get_db_connection()
        conn.execute('INSERT INTO Tarefas (titulo, categoria_id, data_vencimento, recorrencia, descricao, ultima_geracao) VALUES (?, ?, ?, ?, ?, ?)',(titulo, categoria_id, data_vencimento, recorrencia, descricao, ultima_geracao))
        conn.commit()
        conn.close()
        flash(f'Tarefa "{titulo}" adicionada com sucesso!', 'success')
    return redirect(url_for('index'))

@app.route('/complete/<int:id>', methods=['POST'])
def complete_task(id):
    conn = get_db_connection()
    tarefa = conn.execute('SELECT data_vencimento FROM Tarefas WHERE id = ?', (id,)).fetchone()
    data_conclusao = get_agora().strftime('%Y-%m-%d %H:%M:%S')
    concluida_no_prazo = 0
    if tarefa:
        if tarefa['data_vencimento'] is None: concluida_no_prazo = 1
        else:
            data_vencimento = datetime.strptime(tarefa['data_vencimento'], '%Y-%m-%d').date()
            if get_agora().date() <= data_vencimento: concluida_no_prazo = 1
    conn.execute('UPDATE Tarefas SET status = ?, data_conclusao = ?, concluida_no_prazo = ? WHERE id = ?',('Concluída', data_conclusao, concluida_no_prazo, id))
    conn.commit()
    conn.close()
    flash('Tarefa concluída!', 'info')
    return redirect(url_for('index'))

@app.route('/reopen/<int:id>', methods=['POST'])
def reopen_task(id):
    conn = get_db_connection()
    conn.execute("UPDATE Tarefas SET status = 'Pendente', data_conclusao = NULL, concluida_no_prazo = NULL WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    flash('Tarefa reaberta.', 'info')
    return redirect(url_for('index'))

@app.route('/avisos')
def gerenciar_avisos():
    conn = get_db_connection()
    avisos = conn.execute('SELECT * FROM Avisos ORDER BY data_criacao DESC;').fetchall()
    conn.close()
    return render_template('avisos.html', avisos=avisos)

@app.route('/add_aviso', methods=['POST'])
def add_aviso():
    descricao = request.form['descricao']; prioridade = request.form['prioridade']; data_inicio = request.form['data_inicio']; data_fim = request.form['data_fim']
    if descricao and prioridade and data_inicio and data_fim:
        conn = get_db_connection()
        conn.execute('INSERT INTO Avisos (descricao, prioridade, data_inicio, data_fim) VALUES (?, ?, ?, ?)',(descricao, prioridade, data_inicio, data_fim))
        conn.commit()
        conn.close()
        flash('Aviso adicionado com sucesso!', 'success')
    return redirect(url_for('gerenciar_avisos'))

@app.route('/categorias')
def gerenciar_categorias():
    conn = get_db_connection()
    categorias = conn.execute('SELECT * FROM Categorias ORDER BY nome;').fetchall()
    conn.close()
    icones_sugeridos = ['fa-briefcase', 'fa-piggy-bank', 'fa-heart-pulse', 'fa-spa', 'fa-home','fa-paw', 'fa-lightbulb', 'fa-book', 'fa-car', 'fa-plane', 'fa-gift','fa-graduation-cap', 'fa-wrench', 'fa-gavel', 'fa-music', 'fa-utensils']
    return render_template('gerenciar_categorias.html', categorias=categorias, icones_sugeridos=icones_sugeridos)

@app.route('/add_categoria', methods=['POST'])
def add_categoria():
    nome = request.form['nome']; icone = request.form['icone']; cor = request.form['cor']
    if nome:
        conn = get_db_connection()
        conn.execute('INSERT INTO Categorias (nome, icone, cor) VALUES (?, ?, ?)', (nome, icone, cor))
        conn.commit()
        conn.close()
        flash('Categoria adicionada com sucesso!', 'success')
    return redirect(url_for('gerenciar_categorias'))

@app.route('/editar_categoria/<int:id>')
def editar_categoria(id):
    conn = get_db_connection()
    categoria = conn.execute('SELECT * FROM Categorias WHERE id = ?', (id,)).fetchone()
    conn.close()
    icones_sugeridos = [ 'fa-briefcase', 'fa-piggy-bank', 'fa-heart-pulse', 'fa-spa', 'fa-home', 'fa-paw', 'fa-lightbulb', 'fa-book', 'fa-car', 'fa-plane', 'fa-gift', 'fa-graduation-cap', 'fa-wrench', 'fa-gavel', 'fa-music', 'fa-utensils']
    return render_template('editar_categoria.html', categoria=categoria, icones_sugeridos=icones_sugeridos)

@app.route('/update_categoria/<int:id>', methods=['POST'])
def update_categoria(id):
    nome = request.form['nome']; icone = request.form['icone']; cor = request.form['cor']
    if nome:
        conn = get_db_connection()
        conn.execute('UPDATE Categorias SET nome = ?, icone = ?, cor = ? WHERE id = ?',(nome, icone, cor, id))
        conn.commit()
        conn.close()
        flash('Categoria atualizada com sucesso!', 'success')
    return redirect(url_for('gerenciar_categorias'))

@app.route('/delete_categoria/<int:id>', methods=['POST'])
def delete_categoria(id):
    conn = get_db_connection()
    categoria = conn.execute('SELECT nome FROM Categorias WHERE id = ?', (id,)).fetchone()
    conn.execute('DELETE FROM Categorias WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    if categoria:
        flash(f'Categoria "{categoria["nome"]}" deletada.', 'danger')
    return redirect(url_for('gerenciar_categorias'))

@app.route('/historico')
def pagina_historico():
    conn = get_db_connection()
    performance_categorias = conn.execute("SELECT COALESCE(c.nome, 'Sem Categoria') as categoria_nome, c.icone, c.cor, COUNT(t.id) as total_finalizadas, SUM(CASE WHEN t.status = 'Concluída' AND t.concluida_no_prazo = 1 THEN 1 ELSE 0 END) as total_sucessos FROM Tarefas t LEFT JOIN Categorias c ON t.categoria_id = c.id WHERE t.status IN ('Concluída', 'Não Concluída') GROUP BY categoria_nome, icone, cor ORDER BY categoria_nome;").fetchall()
    log_atividades = conn.execute("SELECT titulo, status, data_conclusao, data_vencimento FROM Tarefas WHERE status IN ('Concluída', 'Não Concluída') ORDER BY COALESCE(data_conclusao, data_vencimento) DESC LIMIT 10;").fetchall()
    conn.close()
    return render_template('historico.html',performance_categorias=performance_categorias,log_atividades=log_atividades)

@app.route('/treinos')
def gerenciar_treinos():
    conn = get_db_connection()
    treinos_raw = conn.execute('SELECT * FROM Treinos ORDER BY id;').fetchall()
    exercicios_raw = conn.execute('SELECT * FROM Exercicios ORDER BY id;').fetchall()
    conn.close()
    treinos = []
    for treino in treinos_raw:
        treino_dict = dict(treino)
        treino_dict['exercicios'] = [dict(ex) for ex in exercicios_raw if ex['treino_id'] == treino['id']]
        treinos.append(treino_dict)
    return render_template('gerenciar_treinos.html', treinos=treinos)

@app.route('/add_exercicio', methods=['POST'])
def add_exercicio():
    nome = request.form['nome']; series = request.form['series']; carga_atual = request.form['carga_atual']; observacao = request.form['observacao']; treino_id = request.form['treino_id']
    if nome and treino_id:
        conn = get_db_connection()
        conn.execute('INSERT INTO Exercicios (nome, series, carga_atual, observacao, treino_id) VALUES (?, ?, ?, ?, ?)',(nome, series, carga_atual, observacao, treino_id))
        conn.commit()
        conn.close()
        flash('Exercício adicionado com sucesso!', 'success')
    return redirect(url_for('gerenciar_treinos'))

@app.route('/editar_exercicio/<int:id>')
def editar_exercicio(id):
    conn = get_db_connection()
    exercicio = conn.execute('SELECT * FROM Exercicios WHERE id = ?', (id,)).fetchone()
    conn.close()
    return render_template('editar_exercicio.html', exercicio=exercicio)

@app.route('/update_exercicio/<int:id>', methods=['POST'])
def update_exercicio(id):
    nome = request.form['nome']; series = request.form['series']; carga_atual = request.form['carga_atual']; observacao = request.form['observacao']
    if nome:
        conn = get_db_connection()
        conn.execute('UPDATE Exercicios SET nome = ?, series = ?, carga_atual = ?, observacao = ? WHERE id = ?',(nome, series, carga_atual, observacao, id))
        conn.commit()
        conn.close()
        flash(f'Exercício "{nome}" atualizado!', 'success')
    return redirect(url_for('gerenciar_treinos'))

@app.route('/delete_exercicio/<int:id>', methods=['POST'])
def delete_exercicio(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM Exercicios WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Exercício deletado.', 'danger')
    return redirect(url_for('gerenciar_treinos'))

@app.route('/iniciar_treino/<int:treino_id>', methods=['POST'])
def iniciar_treino(treino_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    data_sessao_formatada = get_agora().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('INSERT INTO TreinoSessoes (treino_id, data_sessao) VALUES (?, ?)', (treino_id, data_sessao_formatada))
    nova_sessao_id = cursor.lastrowid
    conn.commit()
    conn.close()
    flash('Sessão de treino iniciada! Vamos lá!', 'success')
    return redirect(url_for('pagina_sessao', sessao_id=nova_sessao_id))

@app.route('/sessao/<int:sessao_id>')
def pagina_sessao(sessao_id):
    conn = get_db_connection()
    sessao = conn.execute('SELECT * FROM TreinoSessoes WHERE id = ?', (sessao_id,)).fetchone()
    treino = conn.execute('SELECT * FROM Treinos WHERE id = ?', (sessao['treino_id'],)).fetchone()
    exercicios_modelo = conn.execute('SELECT * FROM Exercicios WHERE treino_id = ? ORDER BY id', (sessao['treino_id'],)).fetchall()
    logs_desta_sessao = conn.execute('SELECT * FROM ExercicioLogs WHERE sessao_id = ? ORDER BY id', (sessao_id,)).fetchall()
    conn.close()
    exercicios = []
    for ex_modelo in exercicios_modelo:
        ex_dict = dict(ex_modelo)
        ex_dict['logs'] = [dict(log) for log in logs_desta_sessao if log['exercicio_id'] == ex_dict['id']]
        exercicios.append(ex_dict)
    return render_template('sessao.html', sessao=sessao, treino=treino, exercicios=exercicios)

@app.route('/log_set', methods=['POST'])
def log_set():
    dados = request.get_json()
    sessao_id = dados['sessao_id']; exercicio_id = dados['exercicio_id']; carga = dados['carga']; reps = dados['reps']
    conn = get_db_connection()
    num_series_feitas = conn.execute('SELECT COUNT(id) as count FROM ExercicioLogs WHERE sessao_id = ? AND exercicio_id = ?', (sessao_id, exercicio_id)).fetchone()['count']
    serie_atual = num_series_feitas + 1
    conn.execute('INSERT INTO ExercicioLogs (sessao_id, exercicio_id, serie, carga, reps) VALUES (?, ?, ?, ?, ?)',(sessao_id, exercicio_id, serie_atual, carga, reps))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'serie': serie_atual, 'carga': carga, 'reps': reps})

@app.route('/historico_treinos')
def historico_treinos():
    conn = get_db_connection()
    sessoes = conn.execute("SELECT s.id, s.data_sessao, t.nome as treino_nome FROM TreinoSessoes s JOIN Treinos t ON s.treino_id = t.id ORDER BY s.data_sessao DESC;").fetchall()
    hoje = get_hoje()
    semanas_labels = []
    volumes_por_semana = defaultdict(lambda: defaultdict(float))
    todos_logs = conn.execute("SELECT date(s.data_sessao) as data, t.nome as treino_nome, l.carga, l.reps FROM ExercicioLogs l JOIN TreinoSessoes s ON l.sessao_id = s.id JOIN Treinos t ON s.treino_id = t.id ORDER BY data;").fetchall()
    volume_diario = defaultdict(lambda: defaultdict(float))
    for log in todos_logs:
        volume_diario[log['data']][log['treino_nome']] += log['carga'] * log['reps']
    if todos_logs:
        data_mais_antiga = datetime.strptime(todos_logs[0]['data'], '%Y-%m-%d').date()
        primeira_semana = data_mais_antiga - timedelta(days=data_mais_antiga.weekday())
        data_atual = primeira_semana
        while data_atual <= hoje:
            semanas_labels.append(f"{data_atual.strftime('%d/%m')}")
            for dia in range(7):
                data_dia = data_atual + timedelta(days=dia)
                data_dia_str = data_dia.strftime('%Y-%m-%d')
                if data_dia_str in volume_diario:
                    for treino_nome, volume in volume_diario[data_dia_str].items():
                        volumes_por_semana[semanas_labels[-1]][treino_nome] += volume
            data_atual += timedelta(weeks=1)
    nomes_treinos = sorted([row['nome'] for row in conn.execute("SELECT nome FROM Treinos").fetchall()])
    datasets_grafico = []
    cores = ['#ff8c00', '#20a8d8', '#4dbd74', '#f86c6b', '#6f42c1']
    for i, nome_treino in enumerate(nomes_treinos):
        dataset = {"label": nome_treino, "data": [volumes_por_semana[semana].get(nome_treino, 0) for semana in semanas_labels], "backgroundColor": cores[i % len(cores)]}
        datasets_grafico.append(dataset)
    grafico_evolucao = {"labels": semanas_labels, "datasets": datasets_grafico}
    conn.close()
    return render_template('historico_treinos.html', sessoes=sessoes, grafico_evolucao=grafico_evolucao)

@app.route('/detalhe_sessao/<int:sessao_id>')
def detalhe_sessao(sessao_id):
    conn = get_db_connection()
    sessao = conn.execute('SELECT * FROM TreinoSessoes WHERE id = ?', (sessao_id,)).fetchone()
    treino = conn.execute('SELECT * FROM Treinos WHERE id = ?', (sessao['treino_id'],)).fetchone()
    logs = conn.execute("SELECT l.serie, l.carga, l.reps, e.nome as exercicio_nome, e.id as exercicio_id FROM ExercicioLogs l JOIN Exercicios e ON l.exercicio_id = e.id WHERE l.sessao_id = ? ORDER BY l.id", (sessao_id,)).fetchall()
    conn.close()
    logs_por_exercicio = {}
    for log in logs:
        nome_exercicio = log['exercicio_nome']
        if nome_exercicio not in logs_por_exercicio:
            logs_por_exercicio[nome_exercicio] = {'id': log['exercicio_id'],'logs': []}
        logs_por_exercicio[nome_exercicio]['logs'].append(dict(log))
    data_sessao_obj = datetime.strptime(sessao['data_sessao'], '%Y-%m-%d %H:%M:%S')
    data_sessao_formatada = data_sessao_obj.strftime('%d/%m/%Y às %H:%M')
    return render_template('detalhe_sessao.html',sessao=sessao,treino=treino,logs_por_exercicio=logs_por_exercicio,data_sessao_formatada=data_sessao_formatada)

@app.route('/progresso_exercicio/<int:exercicio_id>')
def progresso_exercicio(exercicio_id):
    conn = get_db_connection()
    exercicio = conn.execute('SELECT nome FROM Exercicios WHERE id = ?', (exercicio_id,)).fetchone()
    historico_carga = conn.execute("SELECT s.data_sessao, MAX(l.carga) as max_carga FROM ExercicioLogs l JOIN TreinoSessoes s ON l.sessao_id = s.id WHERE l.exercicio_id = ? GROUP BY s.id, s.data_sessao ORDER BY s.data_sessao ASC;", (exercicio_id,)).fetchall()
    conn.close()
    next_url = request.args.get('next', url_for('gerenciar_treinos'))
    grafico_labels = [datetime.strptime(row['data_sessao'], '%Y-%m-%d %H:%M:%S').strftime('%d/%m') for row in historico_carga]
    grafico_data = [row['max_carga'] for row in historico_carga]
    dados_grafico = {"labels": grafico_labels, "data": grafico_data}
    return render_template('progresso_exercicio.html',exercicio=exercicio,dados_grafico=dados_grafico,next_url=next_url)

@app.route('/habitos')
def pagina_habitos():
    conn = get_db_connection()
    data_ref_str = request.args.get('data', default=str(get_hoje()))
    data_ref = datetime.strptime(data_ref_str, '%Y-%m-%d').date()
    inicio_da_semana = data_ref - timedelta(days=data_ref.weekday())
    dias_da_semana = [inicio_da_semana + timedelta(days=i) for i in range(7)]
    fim_da_semana = inicio_da_semana + timedelta(days=6)
    semana_anterior = inicio_da_semana - timedelta(days=7)
    semana_seguinte = inicio_da_semana + timedelta(days=7)
    habitos = conn.execute("SELECT * FROM Habitos WHERE ativo = 1 ORDER BY nome").fetchall()
    logs = conn.execute("SELECT habito_id, data_conclusao FROM HabitoLogs WHERE data_conclusao BETWEEN ? AND ?", (inicio_da_semana.strftime('%Y-%m-%d'), fim_da_semana.strftime('%Y-%m-%d'))).fetchall()
    conn.close()
    logs_da_semana = {(log['habito_id'], log['data_conclusao']) for log in logs}
    habitos_com_status = []
    for habito in habitos:
        status_semana = {}
        for dia in dias_da_semana:
            status_semana[dia.strftime('%Y-%m-%d')] = (habito['id'], dia.strftime('%Y-%m-%d')) in logs_da_semana
        habitos_com_status.append({'id': habito['id'], 'nome': habito['nome'], 'status_semana': status_semana})
    semana_atual_formatada = f"{inicio_da_semana.strftime('%d/%m')} - {fim_da_semana.strftime('%d/%m/%Y')}"
    return render_template('habitos.html', habitos=habitos_com_status, dias_da_semana=dias_da_semana, semana_atual_formatada=semana_atual_formatada, semana_anterior=semana_anterior.strftime('%Y-%m-%d'), semana_seguinte=semana_seguinte.strftime('%Y-%m-%d'))

@app.route('/add_habito', methods=['POST'])
def add_habito():
    nome = request.form['nome']
    if nome:
        conn = get_db_connection()
        conn.execute('INSERT INTO Habitos (nome) VALUES (?)', (nome,))
        conn.commit()
        conn.close()
        flash(f'Hábito "{nome}" adicionado!', 'success')
    return redirect(url_for('pagina_habitos'))

@app.route('/toggle_habito', methods=['POST'])
def toggle_habito():
    dados = request.get_json()
    habito_id = dados['habito_id']; data_str = dados['data']
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM HabitoLogs WHERE habito_id = ? AND data_conclusao = ?', (habito_id, data_str))
    if cursor.rowcount > 0:
        status_novo = 'removido'
    else:
        cursor.execute('INSERT INTO HabitoLogs (habito_id, data_conclusao) VALUES (?, ?)', (habito_id, data_str))
        status_novo = 'adicionado'
    conn.commit()
    conn.close()
    return jsonify({'status': status_novo})

@app.route('/gerenciar_tipos_treino')
def gerenciar_tipos_treino():
    conn = get_db_connection()
    treinos = conn.execute("SELECT * FROM Treinos ORDER BY nome").fetchall()
    conn.close()
    return render_template('gerenciar_tipos_treino.html', treinos=treinos)

@app.route('/add_treino', methods=['POST'])
def add_treino():
    nome = request.form['nome']; descricao = request.form['descricao']
    if nome:
        conn = get_db_connection()
        try:
            conn.execute("INSERT INTO Treinos (nome, descricao) VALUES (?, ?)", (nome, descricao))
            conn.commit()
            flash(f'Tipo de Treino "{nome}" adicionado com sucesso!', 'success')
        except sqlite3.IntegrityError:
            flash(f'Erro: O tipo de treino "{nome}" já existe.', 'danger')
        finally:
            conn.close()
    return redirect(url_for('gerenciar_tipos_treino'))

@app.route('/editar_tipo_treino/<int:id>')
def editar_tipo_treino(id):
    conn = get_db_connection()
    treino = conn.execute('SELECT * FROM Treinos WHERE id = ?', (id,)).fetchone()
    conn.close()
    return render_template('editar_tipo_treino.html', treino=treino)

@app.route('/update_tipo_treino/<int:id>', methods=['POST'])
def update_tipo_treino(id):
    nome = request.form['nome']; descricao = request.form['descricao']
    if nome:
        conn = get_db_connection()
        conn.execute('UPDATE Treinos SET nome = ?, descricao = ? WHERE id = ?', (nome, descricao, id))
        conn.commit()
        conn.close()
        flash(f'Tipo de Treino "{nome}" atualizado!', 'success')
    return redirect(url_for('gerenciar_tipos_treino'))

@app.route('/delete_tipo_treino/<int:id>', methods=['POST'])
def delete_tipo_treino(id):
    conn = get_db_connection()
    treino = conn.execute('SELECT nome FROM Treinos WHERE id = ?', (id,)).fetchone()
    conn.execute('DELETE FROM Treinos WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    if treino:
        flash(f'Tipo de Treino "{treino["nome"]}" e todos os seus exercícios e logs foram deletados.', 'danger')
    return redirect(url_for('gerenciar_tipos_treino'))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)