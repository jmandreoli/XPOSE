/* Creation date:        2022-01-15
 * Contributors:         Jean-Marc Andreoli
 * Language:             javascript
 * Purpose:              Xpose: client side manage view
 */

import { addElement, addJButton, addText, toggle_display, unsavedConfirm, deleteConfirm, noopAlert } from './utils.js'

export default class manageView {

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
    { // shadow button
      const button = this.el_shadow = addJButton(menu,'newwin',{title:'Transfer instance->shadow'})
      button.addEventListener('click',()=>{this.shadow()})
    }
    { // infobox
      addText(menu,' Current version: ')
      this.el_version = addElement(menu,'span')
    }
    {
      const div = addElement(this.toplevel,'div')
      this.el_stats = {}
      const table = addElement(div,'table',{class:'manage-stats'})
      const thead = addElement(table,'thead')
      const td = thead.insertRow().insertCell()
      td.colSpan = '2'; td.innerText = 'Statistics'
      const tbody = addElement(table,'tbody')
      {
        const tr = tbody.insertRow()
        tr.insertCell().innerText = 'cats'
        this.el_stats.cat = addElement(tr.insertCell(),'table')
      }
      {
        const tr = tbody.insertRow()
        tr.insertCell().innerText = 'access'
        this.el_stats.access = addElement(tr.insertCell(),'table')
      }
    }
  }

  display () {
    axios({url:`${this.url}/manage`,headers:{'Cache-Control':'no-store'}}).
      then((resp)=>this.display1(resp.data)).
      catch(this.ajaxError)
  }

  display1 (data) {
    if (this.variant) { this.el_shadow.title = 'Transfer shadow->instance'; this.el_shadow.className = 'caution' } // done once never changed
    this.el_version.innerText = `${data.version}[${new Date(data.ts*1000).toISOString()}]`
    const stats = data.stats
    const el_cat = this.el_stats.cat
    el_cat.innerHTML = ''
    for (const [cat,cnt] of Object.entries(stats.cat)) {
      const tr = el_cat.insertRow()
      addText(tr.insertCell(),cat)
      addText(tr.insertCell(),String(cnt))
    }
    const el_access = this.el_stats.access
    el_access.innerHTML = ''
    for (const [access,cnt] of Object.entries(stats.access)) {
      const tr = el_access.insertRow()
      addText(tr.insertCell(),access)
      addText(tr.insertCell(),String(cnt))
    }
    this.show()
  }

  shadow () {
    if (this.variant && !window.confirm('You are about to override the entire Xpose instance.')) { return }
    axios({url:`${this.url}/manage`,method:'POST'}).then(()=>this.toggle_variant()).catch(this.ajaxError)
  }

  close () { this.views.listing.display() }
}
