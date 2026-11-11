const BASE = ''

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: options.body instanceof FormData
      ? undefined
      : { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const data = await res.json()
      detail = typeof data.detail === 'string'
        ? data.detail
        : JSON.stringify(data.detail ?? data)
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  if (res.status === 204) return null
  return res.json()
}

export const api = {
  meters: () => request('/api/meters'),
  createMeter: (body) => request('/api/meters', {
    method: 'POST', body: JSON.stringify(body),
  }),
  readings: (meterId) => request(`/api/meters/${meterId}/readings`),
  addReading: (meterId, body) =>
    request(`/api/meters/${meterId}/readings`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  importReadings: (meterId, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return request(`/api/meters/${meterId}/readings/import`, {
      method: 'POST', body: fd,
    })
  },
  tariffs: () => request('/api/tariffs'),
  createTariff: (body) => request('/api/tariffs', {
    method: 'POST', body: JSON.stringify(body),
  }),
  deleteTariff: (id) => request(`/api/tariffs/${id}`, { method: 'DELETE' }),
  importTariffs: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return request('/api/tariffs/import', { method: 'POST', body: fd })
  },
  holidays: () => request('/api/holidays'),
  addHoliday: (body) => request('/api/holidays', {
    method: 'POST', body: JSON.stringify(body),
  }),
  deleteHoliday: (date) =>
    request(`/api/holidays/${date}`, { method: 'DELETE' }),
  importHolidays: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return request('/api/holidays/import', { method: 'POST', body: fd })
  },
  bills: (meterId) => request(`/api/meters/${meterId}/bills`),
  template: (name) => `/api/templates/${name}.csv`,
}
