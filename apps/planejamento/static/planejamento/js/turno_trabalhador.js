// Atualiza apenas as opções autorizadas, preservando os demais campos digitados.
document.addEventListener('DOMContentLoaded', () => {
    const trabalhador = document.querySelector('select[data-turno-referencia]');
    if (!trabalhador) return;
    const nomeData = trabalhador.dataset.turnoReferencia;
    const data = document.getElementById(`id_${nomeData}`);
    if (!data) return;
    const aviso = document.createElement('span');
    aviso.setAttribute('role', 'status');
    trabalhador.after(aviso);
    let versao = 0;
    let ultimaReferencia = null;
    const atualizar = async () => {
        if (data.value === ultimaReferencia) return;
        ultimaReferencia = data.value;
        const atual = ++versao;
        const url = new URL(window.location.href);
        url.searchParams.set(nomeData, data.value);
        aviso.textContent = ' Atualizando turnos…';
        try {
            const resposta = await fetch(url, {credentials: 'same-origin'});
            if (!resposta.ok || resposta.redirected) throw new Error('Consulta indisponível');
            const pagina = new DOMParser().parseFromString(await resposta.text(), 'text/html');
            const opcoes = pagina.querySelector('select[data-turno-referencia]');
            if (!opcoes) throw new Error('Seletor indisponível');
            if (atual !== versao) return;
            const selecionado = trabalhador.value;
            trabalhador.replaceChildren(...Array.from(opcoes.options, opcao => opcao.cloneNode(true)));
            trabalhador.value = selecionado;
            if (trabalhador.selectedIndex < 0) trabalhador.value = '';
            trabalhador.dispatchEvent(new Event('change', {bubbles: true}));
            aviso.textContent = ' Turnos atualizados para a data informada.';
        } catch (erro) {
            if (atual === versao) {
                ultimaReferencia = null;
                aviso.textContent = ' Não foi possível atualizar os turnos. Confira a data e recarregue o formulário antes de continuar.';
            }
        }
    };
    data.addEventListener('change', atualizar);
    // DateTimeShortcuts altera .value e devolve o foco sem emitir change.
    data.addEventListener('focus', atualizar);
    trabalhador.addEventListener('focus', atualizar);
    document.addEventListener('click', evento => {
        if (evento.target.closest('.datetimeshortcuts, .calendarbox')) atualizar();
    });
    // Também cobre datas preenchidas por GET ou restauradas pelo navegador.
    if (data.value) atualizar();
});
