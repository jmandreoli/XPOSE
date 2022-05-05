/* Creation date:        2022-01-15
 * Contributors:         Jean-Marc Andreoli
 * Language:             javascript
 * Purpose:              Xpose: client side utilities
 */

function human_size (size) {
  // size: int (number of bytes)
  // returns a human readable string representing size
  const thr = 1024.
  const units = ['K','M','G','T','P','E','Z']
  if (size<thr) return `${size}B`
  size /= thr
  for (const u of units) {
    if (size<thr) return `${size.toFixed(2)}${u}iB`
    size /= thr
  }
  return `${size}YiB` // :-)
}

function encodeURIqs(uri,parm) {
  const q = Object.entries(parm).map((x)=>`${encodeURIComponent(x[0])}=${encodeURIComponent(x[1])}`).join('&')
  return `${uri}?${q}`
}

function addElement(container,tag,attrs) {
	const el = document.createElement(tag)
	if (attrs) { for (const [k,v] of Object.entries(attrs)) {el.setAttribute(k,v)} }
	container.appendChild(el)
	return el
}
function addJButton(container,icon,attrs) {
  const button = addElement(container,'button',attrs)
  addElement(button,'span',{class:`ui-icon ui-icon-${icon}`})
  return button
}
function addHeadMark(val,exception,style) {
  if (exception && exception(val)) return
  const [div,div_] = [1,2].map(()=>document.createElement('div')); document.body.prepend(div,div_); div.innerText = val
  const style_ = {position:'fixed',left:'0',right:'0',top:'0',zIndex:'100',backgroundColor:'pink',textAlign:'center',fontSize:'x-large'}
  if (style) { Object.assign(style_,style) }
  Object.assign(div.style,style_)
  Object.assign(div_.style,{height:`${div.offsetHeight}px`})
}
function addText(container,data) {
  const text = document.createTextNode(data||' ')
  container.appendChild(text)
}
function toggle_display (el) { el.style.display = (el.style.display?'':'none') }
function unsavedConfirm () { return window.confirm('Unsaved changes will be lost. Are you sure you want to proceed ?') }
function deleteConfirm () { return window.confirm('Are you sure you want to delete this entry ?') }
function noopAlert () { window.alert('Nothing to save !') }

class AjaxError extends Error {
  name = 'ajax'
  constructor (err) {
    if (err.response) { super(`Server error ${err.response.status} ${err.response.statusText}\n${err.response.data}`) }
    else if (err.request) { super(`No response received from Server\n${err.request.url}`) }
    else { super(err.message) }
  }
}

export { human_size, encodeURIqs, addElement, addJButton, addHeadMark, addText, toggle_display, unsavedConfirm, deleteConfirm, noopAlert, AjaxError }
