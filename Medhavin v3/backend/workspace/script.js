// Light/Dark Toggle Functionality
const toggleButton = document.querySelector('.toggle-button');
const body = document.body;

toggleButton.addEventListener('click', () => {
    body.classList.toggle('light');
});