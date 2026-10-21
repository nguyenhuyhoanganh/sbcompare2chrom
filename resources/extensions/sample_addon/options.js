const box = document.getElementById('opt');
chrome.storage.local.get('opt', v => box.checked = !!v.opt);
box.onchange = () => chrome.storage.local.set({opt: box.checked});
