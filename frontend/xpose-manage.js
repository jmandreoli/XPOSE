/* Creation date:        2022-01-15
 * Contributors:         Jean-Marc Andreoli
 * Language:             javascript
 * Purpose:              Xpose: client side manage view
 */

import { addElement, addJButton, addText, toggle_display, unsavedConfirm, deleteConfirm, noopAlert } from './utils.js'

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
      button.addEventListener('click',()=>{this.close()})
    }
    { // refresh button
      const button = addJButton(menu,'refresh',{title:'Refresh view'})
      button.addEventListener('click',()=>{this.display()})
    }
    { // dump button
      const button = addJButton(menu,'arrowthickstop-1-s',{title:'Dump content'})
      button.addEventListener('click',()=>{window.open(`${this.url}/manage`,'_blank')})
    }
    { // shadow button
      const button = this.el_shadow = addJButton(menu,'newwin',{title:'Transfer instance->shadow'})
      button.addEventListener('click',()=>{this.shadow()})
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

  display () {
    const a = Object.entries(this.stats).map(x=>`${x[0]}=${encodeURIComponent(x[1])}`).join('&')
    axios({url:`${this.url}/manage?${a}`,headers:{'Cache-Control':'no-store'}}).
      then((resp)=>this.display1(resp.data)).
      catch(this.ajaxError)
  }

  display1 (data) {
    if (this.variant) { this.el_shadow.title = 'Transfer shadow->instance'; this.el_shadow.className = 'caution' } // done once never changed
    const meta = data.meta
    this.el_version.innerText = `${meta.root}:${meta.user_version}[${new Date(meta.ts*1000).toISOString()}]`
    for (const [key,el] of Object.entries(this.el_stats)) {
      el.innerHTML = ''
      for (const [val,cnt] of data[key]) {
        const tr = el.insertRow()
        addText(tr.insertCell(),val)
        addText(tr.insertCell(),String(cnt))
      }
    }
    this.show()
  }

  shadow () {
    if (this.variant && !window.confirm('You are about to override the entire Xpose instance.')) { return }
    axios({url:`${this.url}/manage`,method:'POST'}).then(()=>this.toggle_variant()).catch(this.ajaxError)
  }

  close () { this.views.listing.display() }
}
