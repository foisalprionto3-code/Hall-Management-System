document.addEventListener('DOMContentLoaded', function () {
    var revealItems = document.querySelectorAll('.reveal');
    var navLinks = document.querySelectorAll('.landing-links a');
    var sections = document.querySelectorAll('section[id]');

    if (revealItems.length) {
        var revealObserver = new IntersectionObserver(function (entries, observer) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) {
                    return;
                }
                entry.target.classList.add('visible');
                observer.unobserve(entry.target);
            });
        }, {
            threshold: 0.16,
            rootMargin: '0px 0px -8% 0px'
        });

        revealItems.forEach(function (item) {
            revealObserver.observe(item);
        });
    }

    if (!navLinks.length || !sections.length) {
        return;
    }

    function updateActiveSection() {
        var topOffset = window.scrollY + 160;
        var activeId = '';

        sections.forEach(function (section) {
            if (section.offsetTop <= topOffset) {
                activeId = section.id;
            }
        });

        navLinks.forEach(function (link) {
            var href = link.getAttribute('href') || '';
            if (href === '#' + activeId) {
                link.classList.add('active');
            } else {
                link.classList.remove('active');
            }
        });
    }

    updateActiveSection();
    window.addEventListener('scroll', updateActiveSection, { passive: true });
});
