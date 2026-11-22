// Datas da tarefa são informativas; a validação definitiva continua no servidor.
document.addEventListener('DOMContentLoaded', () => {
    const tarefa = document.getElementById('id_tarefa');
    const periodo = document.querySelector('[data-task-period]');
    const mostrarPeriodo = () => {
        const opcao = tarefa?.selectedOptions[0];
        const formatar = valor => valor.split('-').reverse().join('/');
        periodo.textContent = opcao?.dataset.inicio
            ? `Período previsto da tarefa: ${formatar(opcao.dataset.inicio)} a ${formatar(opcao.dataset.fim)}.`
            : 'Selecione uma tarefa para consultar seu período previsto.';
    };
    if (tarefa && periodo) {
        tarefa.addEventListener('change', mostrarPeriodo);
        mostrarPeriodo();
    }
    const menu = document.querySelector('.activity-menu');
    const atualizarAtividades = () => {
        if (!menu) return;
        const nomes = Array.from(menu.querySelectorAll('input:checked'), campo => campo.closest('label').textContent.trim());
        menu.querySelector('summary').textContent = nomes.length
            ? `Atividades da tarefa: ${nomes.join(', ')}` : 'Atividades da tarefa — selecionar';
    };
    menu?.addEventListener('change', atualizarAtividades);
    atualizarAtividades();
    const grupo = document.querySelector('[data-workers]');
    const data = document.getElementById('id_inicio');
    const aviso = document.querySelector('[data-workers-status]');
    if (!grupo || !data || !grupo.dataset.turnoReferencia) return;
    let versao = 0;
    let referencia = data.value;
    const atualizar = async () => {
        if (referencia === data.value) return;
        referencia = data.value;
        const atual = ++versao;
        const url = new URL(window.location.href);
        url.searchParams.set('inicio', data.value);
        aviso.textContent = 'Atualizando trabalhadores e turnos…';
        try {
            const resposta = await fetch(url, {credentials:'same-origin'});
            if (!resposta.ok || resposta.redirected) throw new Error();
            const pagina = new DOMParser().parseFromString(await resposta.text(), 'text/html');
            const novo = pagina.querySelector('[data-workers]');
            if (!novo) throw new Error();
            if (atual !== versao) return;
            const marcados = new Set(Array.from(grupo.querySelectorAll('input:checked'), campo => campo.value));
            const opcoes = novo.querySelectorAll('input[type=checkbox]');
            opcoes.forEach(campo => { campo.checked = marcados.has(campo.value); });
            const mantidos = Array.from(opcoes).filter(campo => campo.checked).length;
            grupo.replaceChildren(...Array.from(novo.childNodes, item => item.cloneNode(true)));
            aviso.textContent = mantidos < marcados.size
                ? 'Turnos atualizados. Algumas seleções deixaram de estar disponíveis; confira os trabalhadores.'
                : 'Trabalhadores e turnos atualizados para a data informada.';
        } catch (erro) {
            if (atual === versao) {
                referencia = null;
                aviso.textContent = 'Não foi possível atualizar os turnos. Confira a data e recarregue antes de continuar.';
            }
        }
    };
    data.addEventListener('change', atualizar);
    data.addEventListener('focus', atualizar);
});
