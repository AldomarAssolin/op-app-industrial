document.addEventListener('DOMContentLoaded', () => {
    const tarefa = document.getElementById('id_tarefa');
    if (!tarefa) return;
    let info = document.getElementById('task-activities-info');
    if (!info) {
        info = document.createElement('p');
        info.id = 'task-activities-info';
        info.setAttribute('role', 'status');
        tarefa.after(info);
    }
    const atualizar = () => {
        const atividades = tarefa.selectedOptions[0]?.dataset.atividades;
        info.textContent = atividades ? `Atividades da tarefa: ${atividades}. Alterações são feitas no cadastro da tarefa.` : 'Escolha a tarefa para consultar suas atividades.';
    };
    tarefa.addEventListener('change', atualizar);
    atualizar();
});
