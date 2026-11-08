/* Dossier — Desktop surface.
 *
 * The Desktop half talks to Python over HTTP only: every call here is a route
 * in dashboard/plugin_api.py, mounted at /api/plugins/dossier. There is no
 * direct callback into plugin Python, and this file does not reach into the
 * app's DOM, storage or internal stores.
 *
 * No JSX: this module is loaded uncompiled, so markup is built with
 * jsx()/jsxs() from react/jsx-runtime.
 */

import * as sdk from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ROUTES = sdk.ROUTES_AREA || 'routes'
const NAV = sdk.SIDEBAR_NAV_AREA || 'sidebar.nav'
const PAGE_PATH = '/dossiers'

const S = {
  wrap: { display: 'flex', height: '100%', minHeight: 0, font: 'inherit' },
  list: {
    width: '300px',
    flexShrink: 0,
    borderRight: '1px solid var(--ui-border, rgba(128,128,128,0.3))',
    overflowY: 'auto',
    padding: '12px',
  },
  main: { flex: 1, overflowY: 'auto', padding: '20px 24px', minWidth: 0 },
  item: (active) => ({
    display: 'block',
    width: '100%',
    textAlign: 'left',
    padding: '8px 10px',
    marginBottom: '4px',
    borderRadius: '6px',
    border: 'none',
    cursor: 'pointer',
    background: active ? 'var(--ui-selection, rgba(128,128,128,0.2))' : 'transparent',
    color: 'inherit',
    font: 'inherit',
  }),
  h1: { fontSize: '18px', fontWeight: 600, margin: '0 0 4px' },
  meta: { opacity: 0.65, fontSize: '12px', marginBottom: '16px' },
  h2: {
    fontSize: '11px',
    letterSpacing: '0.08em',
    textTransform: 'uppercase',
    opacity: 0.65,
    margin: '18px 0 6px',
  },
  li: { marginBottom: '4px', lineHeight: 1.45 },
  button: {
    padding: '5px 11px',
    marginRight: '8px',
    borderRadius: '6px',
    border: '1px solid var(--ui-border, rgba(128,128,128,0.35))',
    background: 'transparent',
    color: 'inherit',
    cursor: 'pointer',
    font: 'inherit',
    fontSize: '12px',
  },
  note: { opacity: 0.7, fontSize: '12px', marginTop: '10px', lineHeight: 1.5 },
}

function DossierPage() {
  const [items, setItems] = useState([])
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)
  const [busy, setBusy] = useState(false)
  const [armed, setArmed] = useState(false)
  const [note, setNote] = useState('')

  async function loadList() {
    try {
      const data = await ctxRest('/dossiers')
      setItems((data && data.items) || [])
    } catch (err) {
      setNote('Could not load dossiers: ' + String(err && err.message ? err.message : err))
    }
  }

  async function loadDetail(id) {
    setSelected(id)
    setArmed(false)
    try {
      setDetail(await ctxRest('/dossiers/' + id))
    } catch (err) {
      setNote('Could not load that dossier: ' + String(err && err.message ? err.message : err))
    }
  }

  useEffect(() => {
    loadList()
  }, [])

  async function refresh() {
    if (!selected) return
    setBusy(true)
    setNote('')
    try {
      const result = await ctxRest('/dossiers/' + selected + '/refresh', { method: 'POST', body: {} })
      if (result && result.ok) {
        const diff = result.diff
        const changed = diff ? diff.changed_count : 0
        setNote(changed ? 'Refreshed. ' + changed + ' change(s) since the last snapshot.' : 'Refreshed. No changes.')
        await loadDetail(selected)
        await loadList()
      } else {
        setNote((result && result.reason) || 'Refresh did not run.')
      }
    } catch (err) {
      setNote('Refresh failed: ' + String(err && err.message ? err.message : err))
    } finally {
      setBusy(false)
    }
  }

  async function forget() {
    if (!selected) return
    if (!armed) {
      setArmed(true)
      setNote('Press Forget again to delete this dossier permanently.')
      return
    }
    setBusy(true)
    try {
      await ctxRest('/dossiers/' + selected + '/forget', { method: 'POST', body: { confirm: true } })
      setSelected(null)
      setDetail(null)
      setNote('Deleted.')
      await loadList()
    } catch (err) {
      setNote('Delete failed: ' + String(err && err.message ? err.message : err))
    } finally {
      setBusy(false)
      setArmed(false)
    }
  }

  const list = jsx('div', {
    style: S.list,
    children: items.length
      ? items.map((item) =>
          jsxs(
            'button',
            {
              style: S.item(item.id === selected),
              onClick: () => loadDetail(item.id),
              children: [
                jsx('div', { children: item.canonical_name }),
                jsx('div', {
                  style: { opacity: 0.6, fontSize: '11px' },
                  children:
                    (item.claims || 0) +
                    ' claim(s)' +
                    (item.contested ? ' · ' + item.contested + ' contested' : '') +
                    (item.last_snapshot ? ' · ' + String(item.last_snapshot).slice(0, 10) : ''),
                }),
              ],
            },
            String(item.id)
          )
        )
      : jsx('div', { style: S.note, children: 'No dossiers yet. Ask for one in a session: /dossier <name>' }),
  })

  const body = !detail
    ? jsxs('div', {
        children: [
          jsx('h1', { style: S.h1, children: 'Dossiers' }),
          jsx('div', {
            style: S.meta,
            children: 'Pick one to read it, or build a new one in a session with /dossier <name>.',
          }),
        ],
      })
    : jsxs('div', {
        children: [
          jsx('h1', { style: S.h1, children: detail.entity.canonical_name }),
          jsx('div', {
            style: S.meta,
            children:
              (detail.entity.kind || 'org') +
              (detail.entity.domain ? ' · ' + detail.entity.domain : '') +
              (detail.generated_at ? ' · snapshot ' + String(detail.generated_at).slice(0, 10) : ''),
          }),
          jsxs('div', {
            style: { marginBottom: '14px' },
            children: [
              jsx('button', {
                style: S.button,
                disabled: busy,
                onClick: refresh,
                children: busy ? 'Working…' : 'Refresh',
              }),
              jsx('button', {
                style: S.button,
                disabled: busy,
                onClick: forget,
                children: armed ? 'Really forget' : 'Forget',
              }),
            ],
          }),
          detail.headline ? jsx('p', { style: S.li, children: detail.headline }) : null,
          ...(detail.sections || [])
            .filter((section) => section.id !== 'sources')
            .map((section) =>
              jsxs(
                'div',
                {
                  children: [
                    jsx('h2', { style: S.h2, children: section.title }),
                    section.bullets && section.bullets.length
                      ? jsx('ul', {
                          style: { margin: 0, paddingLeft: '18px' },
                          children: section.bullets.map((bullet, i) =>
                            jsx('li', { style: S.li, children: clean(bullet.text) }, String(i))
                          ),
                        })
                      : jsx('div', { style: S.note, children: clean(section.note || 'Nothing supported.') }),
                  ],
                },
                section.id
              )
            ),
          note ? jsx('div', { style: S.note, children: note }) : null,
        ],
      })

  return jsxs('div', { style: S.wrap, children: [list, jsx('div', { style: S.main, children: body })] })
}

/* The brief is composed in Markdown-ish bold; the Desktop renders plain text. */
function clean(text) {
  return String(text || '').replace(/\*\*/g, '')
}

/* ctx.rest is bound per plugin in register(); the page needs it after mount. */
let ctxRest = () => Promise.reject(new Error('plugin context not ready'))

export default {
  id: 'dossier',
  name: 'Dossier',
  description: 'Sourced, dated briefs on organisations and people, with what changed since.',
  defaultEnabled: true,
  capabilities: {},
  register(ctx) {
    ctxRest = (path, options) => ctx.rest(path, options)

    ctx.register({
      id: 'dossier.page',
      area: ROUTES,
      title: 'Dossiers',
      data: { path: PAGE_PATH },
      render: () => jsx(DossierPage, {}),
    })

    ctx.register({
      id: 'dossier.nav',
      area: NAV,
      order: 60,
      data: { path: PAGE_PATH, label: 'Dossiers', codicon: 'book' },
    })
  },
}
