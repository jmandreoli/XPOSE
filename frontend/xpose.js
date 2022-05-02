/* Creation date:        2022-01-15
 * Contributors:         Jean-Marc Andreoli
 * Language:             javascript
 * Purpose:              Xpose: a JSON database manager (client side)
 */

import { addElement, addJButton, addText, unsavedConfirm } from './utils.js'
import listingView from './xpose-listing.js'
import entryView from './xpose-entry.js'
import attachView from './xpose-attach.js'
import manageView from './xpose-manage.js'

//
// Xpose
//

class Xpose {
  constructor (config) {
    this.url = config.url
    this.dataUrl = config.data
    this.current = null
    this.dirty = false
    this.variant = (document.cookie.split('; ').find(row=>row.startsWith('xpose-variant='))||'').substr(14)
    const views = config.views||{}
    this.views = {}
    const default_views = { listing:listingView, entry:entryView, attach:attachView, manage:manageView }
    for (const [name,default_factory] of Object.entries(default_views)) { this.addView(name,new (views[name]||default_factory)()) }
    window.addEventListener('beforeunload',(e)=>{ if (this.dirty) {e.preventDefault();e.returnValue=''} })
  }
  addView (name,view) {
    view.onerror = (err) => this.onerror(name,err)
    view.progressor = (label) => this.progressor(`${name}:${label}`)
    view.variant = this.variant
    view.toggle_variant = () => this.toggle_variant()
    view.set_dirty = (flag) => { this.dirty = flag; view.show_dirty(flag); }
    view.get_dirty = () => this.dirty
    view.confirm_dirty = () => this.dirty && !unsavedConfirm()
    view.show = () => this.show(view)
    view.url = this.url
    view.dataUrl = this.dataUrl
    view.views = this.views
    view.name = name
    this.views[name] = view
    view.toplevel.style.display = 'none'
  }
  show (view) {
    if (this.current===view) return
    if (this.current!==null) { this.current.toplevel.style.display = 'none' }
    this.current = view
    this.el_view.innerText = view.name
    this.current.toplevel.style.display = ''
  }

  progressor (label) {
    // displays a progress bar and returns an object with the following fields:
    //   update: an update callback to pass to the target task (argument: percent_complete)
    //   close: a close callback (no argument)
    const div = addElement(this.el_progress,'div')
    const el = addElement(div,'progress',{max:'1.',value:'0.',})
    const button = addJButton(div,'closethick',{title:'Interrupt upload'})
    addText(div,label)
    let cancelled = false
    button.addEventListener('click',()=>{cancelled=true})
    return {
      update:(percent)=>{el.value=percent.toFixed(3);return cancelled},
      close:()=>{this.el_progress.removeChild(div)}
    }
  }
  async onerror (label,err) {
    this.console.lastElementChild.innerText = `ERROR[${label}]: ${err.name}\n${err.message}\n${err.stack}`
    this.console.style.display = ''
    throw err // so it still appears in the js console
  }
  toggle_variant () { document.cookie=`xpose-variant=${this.variant?'':'shadow'}`;window.location.reload() }
  render() {
    {
      this.el_progress = addElement(document.body,'div',{class:'xpose-progress'})
    }
    {
      const h1 = addElement(document.body,'h1')
      addText(h1,'Xpose: ')
      this.el_view = addElement(h1,'span')
    }
    {
      this.console = addElement(document.body,'div',{class:'caution',style:'position:absolute; left:0; right:0; z-index:100; display:none'})
      const button = addJButton(this.console,'close',{class:'caution',style:'float:right'})
      button.addEventListener('click',()=>{this.console.style.display='none'})
      addElement(this.console,'div',{class:'console'})
    }
    {
      if (this.variant) {
        const warning = addElement(document.body,'div',{class:'xpose-variant-warning'})
        addText(warning,this.variant)
        addJButton(warning,'close').addEventListener('click',()=>this.toggle_variant())
      }
    }
    for (const view of Object.values(this.views)) { document.body.appendChild(view.toplevel) }
    this.views.listing.display()
  }
}

export { Xpose, listingView, entryView, attachView, manageView }
