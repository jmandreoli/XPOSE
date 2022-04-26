/* Creation date:        2022-01-15
 * Contributors:         Jean-Marc Andreoli
 * Language:             javascript
 * Purpose:              Xpose: client side manage view
 */

import { encodeURIqs, addElement, addJButton, addText, AjaxError } from './utils.js'

export default class manageView {

  stats = {
    cat:'SELECT cat as val,count(*) as cnt FROM Entry GROUP BY val ORDER BY cnt DESC',
    access:'SELECT coalesce(access,\'\') as val,count(*) as cnt FROM Entry GROUP BY val ORDER BY cnt DESC'
  }

  constructor () {
    this.toplevel = document.createElement('div')
    const menu = addElement(this.toplevel,'div')
    { // return button
      const button = addJButton(menu,'arrowreturnthick-1-w',{title:'Return to listing view'})
      button.addEventListener('click',()=>this.close().catch(err=>this.onerror(err)))
    }
    { // refresh button
      const button = addJButton(menu,'refresh',{title:'Refresh view'})
      button.addEventListener('click',()=>this.display().catch(err=>this.onerror(err)))
    }
    { // dump button
      const button = addJButton(menu,'arrowthickstop-1-s',{title:'Dump content'})
      button.addEventListener('click',()=>window.open(`${this.url}/manage`,'_blank'))
    }
    { // shadow button
      const button = this.el_shadow = addJButton(menu,'newwin',{title:'Transfer instance->shadow'})
      button.addEventListener('click',()=>this.shadow().catch(err=>this.onerror(err)))
    }
    { // infobox
      addText(menu,' Xpose instance: ')
      this.el_version = addElement(menu,'b')
    }
    {
      const div = addElement(this.toplevel,'div')
      this.el_stats = {}
      const table = addElement(div,'table',{class:'manage-stats'})
      const thead = addElement(table,'thead')
      const td = thead.insertRow().insertCell()
      td.colSpan = '2'; td.innerText = 'Statistics'
      const tbody = addElement(table,'tbody')
      for (const key of Object.keys(this.stats)) {
        const tr = tbody.insertRow()
        tr.insertCell().innerText = key
        this.el_stats[key] = addElement(tr.insertCell(),'table')
      }
    }
  }

  async display () {
    const resp = await axios({url:encodeURIqs(`${this.url}/manage`,this.stats),headers:{'Cache-Control':'no-store'}}).
      catch(err=>{throw new AjaxError(err)})
    if (this.variant) { this.el_shadow.title = 'Transfer shadow->instance'; this.el_shadow.className = 'caution' } // done once never changed
    const meta = resp.data.meta
    this.el_version.innerText = `${meta.root}:${meta.user_version}[${new Date(meta.ts*1000).toISOString()}]`
    for (const [key,el] of Object.entries(this.el_stats)) {
      el.innerHTML = ''
      for (const r of resp.data[key]) {
        const tr = el.insertRow()
        addText(tr.insertCell(),r.val)
        addText(tr.insertCell(),String(r.cnt))
      }
    }
    this.show()
  }

  async shadow () {
    if (this.variant && !window.confirm('You are about to override the entire Xpose instance.')) { return }
    await axios({url:`${this.url}/manage`,method:'POST'}).catch(err=>{throw new AjaxError(err)})
    this.toggle_variant()
  }

  async close () { await this.views.listing.display() }
}
