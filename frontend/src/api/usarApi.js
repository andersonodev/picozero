// frontend/src/api/usarApi.js
// Hook de leitura: const { dados, carregando, erro, origem, recarregar } = usarApi(() => api.riscos(unidade), [unidade])
// origem = 'api' (motor) ou 'previa' (fallback local); a tela pode mostrar um selo "prévia offline".
import { useCallback, useEffect, useState } from 'react'

export function usarApi(fn, deps = []) {
  const [estado, setEstado] = useState({ dados: null, carregando: true, erro: null, origem: null })
  const [versao, setVersao] = useState(0)

  useEffect(() => {
    let vivo = true
    setEstado((e) => ({ ...e, carregando: true }))
    fn().then((r) => {
      if (vivo) setEstado({ dados: r.dados, origem: r.origem, erro: r.erro || null, carregando: false })
    })
    return () => {
      vivo = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, versao])

  const recarregar = useCallback(() => setVersao((v) => v + 1), [])
  return { ...estado, recarregar }
}
