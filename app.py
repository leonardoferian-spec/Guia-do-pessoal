from flask import Flask, render_template, request, jsonify
import sqlite3
import os

app = Flask(__name__)
DB_NAME = 'natal.db'

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS ideas
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, sector TEXT, idea TEXT, status TEXT)''')
        
        # Inserir dados iniciais se estiver vazio
        c.execute('SELECT COUNT(*) FROM ideas')
        if c.fetchone()[0] == 0:
            iniciais = [
                ('Jardim', 'Pisca Pisca', 'pendente'),
                ('Jardim', 'Boneco de neve', 'pendente'),
                ('Hall de Entrada', 'Papai Noel Descendo (só perninhas)', 'pendente'),
                ('Hall de Entrada', 'Refletores vermelho e verde', 'pendente'),
                ('Hall do auditorio/Bloco A', 'Arvore espiral', 'pendente'),
                ('Hall do auditorio/Bloco A', 'Enfeite', 'pendente'),
                ('Refeitorio', 'Geladeira enfeitada', 'pendente'),
                ('Refeitorio', 'Nuvem de palavras na TV (QR Code e Real Time)', 'pendente'),
                ('area jardim', 'Fita arvore', 'pendente'),
                ('area jardim', 'Boneco de neve', 'pendente'),
                ('area jardim', 'Pisca pisca tipo represa (em fita)', 'pendente'),
                ('biblioteca', '+ facilidade de ideias/decorações', 'pendente'),
                ('area externa', 'Enfeites pinheiro', 'pendente'),
                ('porta sala de aula', 'Bengalas', 'pendente'),
                ('porta sala de aula', 'Grilanda/Papai Noel', 'pendente')
            ]
            c.executemany('INSERT INTO ideas (sector, idea, status) VALUES (?, ?, ?)', iniciais)
        conn.commit()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/ideas', methods=['GET'])
def get_ideas():
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT * FROM ideas')
        ideas = [dict(row) for row in c.fetchall()]
    return jsonify(ideas)

@app.route('/api/ideas', methods=['POST'])
def add_idea():
    data = request.json
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('INSERT INTO ideas (sector, idea, status) VALUES (?, ?, ?)', 
                  (data['sector'], data['idea'], 'pendente'))
        conn.commit()
        return jsonify({'id': c.lastrowid}), 201

@app.route('/api/ideas/<int:idea_id>', methods=['PUT'])
def update_idea(idea_id):
    data = request.json
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('UPDATE ideas SET status = ? WHERE id = ?', (data['status'], idea_id))
        conn.commit()
    return jsonify({'success': True})

@app.route('/api/ideas/<int:idea_id>', methods=['DELETE'])
def delete_idea(idea_id):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute('DELETE FROM ideas WHERE id = ?', (idea_id,))
        conn.commit()
    return jsonify({'success': True})

if __name__ == '__main__':
    init_db()
    # Usando a porta definida pelo ambiente (útil para deploy) ou 5000 localmente
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
