from datetime import date, datetime
import streamlit as st


st.set_page_config(
    page_title='Acompanhamento de Turnos GO',
    page_icon='📊',
    layout='wide',
)

GRUPOS = ['GOOL', 'GOOC', 'GOOK', 'GOOH']
MESES = [
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
]

SQL_TURNOS = """
SELECT
    TO_DATE(h.HTP_INICIO_TURNO) AS DATA,
    SUBSTR(UPPER(TRIM(p.PRX_DESCRICAO)), 1, 4) AS GRUPO,
    UPPER(TRIM(p.PRX_DESCRICAO)) AS PREFIXO,
    h.HTP_INICIO_TURNO AS INICIO_TURNO,
    h.HTP_SAIDA_PREVISTA AS SAIDA_PREVISTA,
    h.HTP_FIM_TURNO AS FIM_TURNO,
    IFF(h.HTP_FIM_TURNO IS NULL, 'EM ANDAMENTO', 'ENCERRADO') AS SITUACAO,
    ROUND(DATEDIFF('SECOND', h.HTP_INICIO_TURNO, h.HTP_FIM_TURNO) / 3600.0, 2)
        AS DURACAO_HORAS,
    DATEDIFF('MINUTE', h.HTP_SAIDA_PREVISTA, h.HTP_FIM_TURNO)
        AS DIFERENCA_FECHAMENTO_MIN,
    p.PARTICIPA_ESCALA,
    h.HTP_OBSERVACAO AS OBSERVACAO,
    p.PREFIXO_TURMA_ID,
    h.HIST_TURMA_PLANTAO_ID
FROM EQTLINFO_RAW.OPER_GO.HISTORICO_TURMA_PLANTAO h
JOIN EQTLINFO_RAW.OPER_GO.PREFIXO_TURMA p
    ON p.PREFIXO_TURMA_ID = h.PREFIXO_TURMA_ID
WHERE SUBSTR(UPPER(TRIM(p.PRX_DESCRICAO)), 1, 4)
      IN ('GOOL', 'GOOC', 'GOOK', 'GOOH')
  AND h.HTP_INICIO_TURNO >= ?
  AND h.HTP_INICIO_TURNO < ?
ORDER BY h.HTP_INICIO_TURNO, p.PRX_DESCRICAO, h.HIST_TURMA_PLANTAO_ID
"""


def proximo_mes(ano, mes):
    return date(ano + (mes == 12), 1 if mes == 12 else mes + 1, 1)


def carregar_turnos(inicio, fim):
    conexao = st.connection('snowflake')
    return conexao.session().sql(SQL_TURNOS, params=[inicio, fim]).to_pandas()


st.title('Acompanhamento de Turnos GO')
st.caption('Abertura e fechamento reais das equipes')

ano = st.sidebar.number_input('Ano', min_value=2020, max_value=2100, value=date.today().year)
mes = st.sidebar.selectbox(
    'Mês', options=range(1, 13), index=date.today().month - 1,
    format_func=lambda valor: MESES[valor - 1]
)
inicio = date(ano, mes, 1)
fim = proximo_mes(ano, mes)
chave = (ano, mes)

if st.sidebar.button('Atualizar dados', type='primary'):
    st.session_state.pop('turnos', None)

if st.session_state.get('periodo') != chave:
    st.session_state.pop('turnos', None)

if 'turnos' not in st.session_state:
    try:
        with st.spinner('Consultando os turnos no Snowflake…'):
            st.session_state['turnos'] = carregar_turnos(inicio, fim)
            st.session_state['periodo'] = chave
            st.session_state['consultado_em'] = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
    except Exception as erro:
        st.error('Não foi possível consultar os dados no Snowflake.')
        st.code(str(erro))
        st.stop()

dados = st.session_state['turnos'].copy()
st.caption('Última consulta: ' + st.session_state['consultado_em'])

grupos = st.sidebar.multiselect('Grupos', GRUPOS, default=GRUPOS)
if not grupos:
    st.info('Selecione pelo menos um grupo.')
    st.stop()

filtrado = dados[dados['GRUPO'].isin(grupos)].copy()
equipes = st.sidebar.multiselect(
    'Equipes', sorted(filtrado['PREFIXO'].dropna().unique())
)
if equipes:
    filtrado = filtrado[filtrado['PREFIXO'].isin(equipes)]

situacoes = st.sidebar.multiselect(
    'Situação', ['EM ANDAMENTO', 'ENCERRADO'],
    default=['EM ANDAMENTO', 'ENCERRADO']
)
filtrado = filtrado[filtrado['SITUACAO'].isin(situacoes)]

duplicados = filtrado['HIST_TURMA_PLANTAO_ID'].duplicated(keep=False)
if duplicados.any():
    quantidade = filtrado.loc[duplicados, 'HIST_TURMA_PLANTAO_ID'].nunique()
    st.warning(f'{quantidade} histórico(s) aparecem mais de uma vez no resultado.')

metricas = st.columns(4)
metricas[0].metric('Turnos', filtrado['HIST_TURMA_PLANTAO_ID'].nunique())
metricas[1].metric('Equipes', filtrado['PREFIXO'].nunique())
metricas[2].metric('Em andamento', int(filtrado['SITUACAO'].eq('EM ANDAMENTO').sum()))
mediana = filtrado['DURACAO_HORAS'].median()
metricas[3].metric('Duração mediana', '—' if mediana != mediana else f'{mediana:.1f} h')

aba_turnos, aba_resumo = st.tabs(['Turnos', 'Resumo diário'])

colunas_visiveis = [
    'DATA', 'GRUPO', 'PREFIXO', 'INICIO_TURNO', 'SAIDA_PREVISTA',
    'FIM_TURNO', 'SITUACAO', 'DURACAO_HORAS',
    'DIFERENCA_FECHAMENTO_MIN', 'PARTICIPA_ESCALA', 'OBSERVACAO'
]

with aba_turnos:
    st.subheader(f'Turnos de {MESES[mes - 1]} de {ano}')
    st.caption(
        'Diferença positiva: fechamento depois da saída prevista. '
        'Diferença negativa: fechamento antes da saída prevista.'
    )
    st.dataframe(
        filtrado[colunas_visiveis],
        hide_index=True,
        use_container_width=True,
        height=620,
        column_config={
            'DATA': st.column_config.DateColumn('Data', format='DD/MM/YYYY'),
            'INICIO_TURNO': st.column_config.DatetimeColumn('Abertura', format='DD/MM/YYYY HH:mm'),
            'SAIDA_PREVISTA': st.column_config.DatetimeColumn('Saída prevista', format='DD/MM/YYYY HH:mm'),
            'FIM_TURNO': st.column_config.DatetimeColumn('Fechamento', format='DD/MM/YYYY HH:mm'),
            'DURACAO_HORAS': st.column_config.NumberColumn('Duração (h)', format='%.2f'),
            'DIFERENCA_FECHAMENTO_MIN': st.column_config.NumberColumn(
                'Diferença fechamento (min)', format='%d'
            ),
        },
    )

with aba_resumo:
    st.subheader('Quantidade de turnos abertos por dia')
    if filtrado.empty:
        st.info('Nenhum turno encontrado para os filtros selecionados.')
    else:
        resumo = filtrado.pivot_table(
            index='DATA', columns='GRUPO', values='HIST_TURMA_PLANTAO_ID',
            aggfunc='nunique', fill_value=0
        ).reindex(columns=GRUPOS, fill_value=0)
        resumo['TOTAL'] = resumo.sum(axis=1)
        st.dataframe(resumo, use_container_width=True)
        st.line_chart(resumo[grupos])

st.download_button(
    'Baixar tabela filtrada em CSV',
    filtrado[colunas_visiveis].to_csv(index=False, sep=';', decimal=',').encode('utf-8-sig'),
    file_name=f'acompanhamento_turnos_{ano}_{mes:02}.csv',
    mime='text/csv',
)
