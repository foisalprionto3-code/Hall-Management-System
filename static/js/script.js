// Sidebar + Alerts Center behavior
document.addEventListener('DOMContentLoaded', function () {
    const hamburger = document.getElementById('hamburger');
    const sidebar = document.getElementById('sidebar');
    const sidebarOverlay = document.getElementById('sidebarOverlay');
    const closeSidebar = document.getElementById('closeSidebar');
    const sidebarLinks = sidebar ? sidebar.querySelectorAll('a') : [];

    const notificationToggle = document.getElementById('notificationToggle');
    const notificationBadge = document.getElementById('notificationBadge');
    const notificationPanel = document.getElementById('notificationPanel');
    const notificationOverlay = document.getElementById('notificationOverlay');
    const closeNotificationPanel = document.getElementById('closeNotificationPanel');
    const notificationsList = document.getElementById('notificationsList');
    const noticesList = document.getElementById('noticesList');
    const markAllReadBtn = document.getElementById('markAllReadBtn');
    const panelActions = document.getElementById('notificationPanelActions');
    const tabButtons = document.querySelectorAll('.notification-tab');

    const alertState = {
        activeTab: 'notifications',
        notifications: [],
        notices: []
    };

    if (hamburger && window.innerWidth > 768) {
        hamburger.classList.add('active');
    }

    if (hamburger && sidebar && sidebarOverlay) {
        hamburger.addEventListener('click', function () {
            if (window.innerWidth > 768) {
                sidebar.classList.toggle('collapsed');
                document.querySelector('.main-content').classList.toggle('expanded');
                if (sidebar.classList.contains('collapsed')) {
                    hamburger.classList.remove('active');
                } else {
                    hamburger.classList.add('active');
                }
            } else {
                hamburger.classList.toggle('active');
                sidebar.classList.toggle('active');
                sidebarOverlay.classList.toggle('active');
            }
            updateBodyScroll();
        });
    }

    if (sidebarOverlay && hamburger && sidebar) {
        sidebarOverlay.addEventListener('click', function () {
            hamburger.classList.remove('active');
            sidebar.classList.remove('active');
            sidebarOverlay.classList.remove('active');
        });
    }

    if (closeSidebar && hamburger && sidebar && sidebarOverlay) {
        closeSidebar.addEventListener('click', function () {
            hamburger.classList.remove('active');
            sidebar.classList.remove('active');
            sidebarOverlay.classList.remove('active');
        });
    }

    sidebarLinks.forEach(function (link) {
        link.addEventListener('click', function () {
            if (window.innerWidth <= 768 && hamburger && sidebar && sidebarOverlay) {
                hamburger.classList.remove('active');
                sidebar.classList.remove('active');
                sidebarOverlay.classList.remove('active');
            }
        });
    });

    window.addEventListener('resize', function () {
        if (!sidebar || !sidebarOverlay || !hamburger) {
            return;
        }

        if (window.innerWidth > 768) {
            sidebar.classList.remove('active');
            sidebarOverlay.classList.remove('active');
            if (!sidebar.classList.contains('collapsed')) {
                hamburger.classList.add('active');
            } else {
                hamburger.classList.remove('active');
            }
        } else {
            if (!sidebar.classList.contains('active')) {
                hamburger.classList.remove('active');
            } else {
                hamburger.classList.add('active');
            }
        }
        updateBodyScroll();
    });

    const originalOverflow = document.body.style.overflow;
    function updateBodyScroll() {
        const sidebarOpen = sidebar && sidebar.classList.contains('active') && window.innerWidth <= 768;
        const panelOpen = notificationPanel && notificationPanel.classList.contains('open') && window.innerWidth <= 768;

        if (sidebarOpen || panelOpen) {
            document.body.style.overflow = 'hidden';
        } else {
            document.body.style.overflow = originalOverflow || 'auto';
        }
    }

    function escapeHtml(value) {
        if (value === null || value === undefined) {
            return '';
        }

        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function formatDateLabel(value) {
        if (!value) {
            return 'Unknown time';
        }

        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) {
            return value;
        }

        return parsed.toLocaleString();
    }

    function setBadge(unreadCount) {
        if (!notificationBadge) {
            return;
        }

        if (unreadCount > 0) {
            notificationBadge.textContent = unreadCount > 99 ? '99+' : String(unreadCount);
            notificationBadge.classList.add('visible');
        } else {
            notificationBadge.textContent = '0';
            notificationBadge.classList.remove('visible');
        }
    }

    function renderNotifications() {
        if (!notificationsList) {
            return;
        }

        if (!alertState.notifications.length) {
            notificationsList.innerHTML = '<div class="notification-empty">No notifications yet.</div>';
            return;
        }

        notificationsList.innerHTML = alertState.notifications.map(function (item) {
            const unreadClass = item.is_read ? '' : ' unread';
            const actionHtml = item.is_read
                ? ''
                : '<button type="button" class="notice-action-btn mark-read-btn" data-id="' + item.id + '">Mark read</button>';

            return '<article class="notification-item' + unreadClass + '">' +
                '<div class="notification-item-content">' +
                '<p class="notification-item-message">' + escapeHtml(item.message) + '</p>' +
                '<span class="notification-item-time">' + escapeHtml(formatDateLabel(item.created_at)) + '</span>' +
                '</div>' +
                '<div class="notification-item-actions">' + actionHtml + '</div>' +
                '</article>';
        }).join('');
    }

    function renderNotices() {
        if (!noticesList) {
            return;
        }

        if (!alertState.notices.length) {
            noticesList.innerHTML = '<div class="notification-empty">No active notices.</div>';
            return;
        }

        noticesList.innerHTML = alertState.notices.map(function (item) {
            const pinnedTag = item.is_pinned ? '<span class="notice-tag">Pinned</span>' : '';
            const roleTag = '<span class="notice-role">' + escapeHtml(item.target_role) + '</span>';
            const expiresText = item.expires_at
                ? '<div class="notice-extra">Expires: ' + escapeHtml(formatDateLabel(item.expires_at)) + '</div>'
                : '';

            return '<article class="notice-item">' +
                '<div class="notice-item-top">' +
                '<h4>' + escapeHtml(item.title) + '</h4>' +
                '<div class="notice-item-tags">' + pinnedTag + roleTag + '</div>' +
                '</div>' +
                '<p>' + escapeHtml(item.message) + '</p>' +
                '<div class="notice-extra">Posted: ' + escapeHtml(formatDateLabel(item.created_at)) + '</div>' +
                expiresText +
                '</article>';
        }).join('');
    }

    function setTab(tabName) {
        alertState.activeTab = tabName;

        tabButtons.forEach(function (button) {
            const isActive = button.dataset.tab === tabName;
            button.classList.toggle('active', isActive);
            button.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });

        if (notificationsList) {
            notificationsList.classList.toggle('hidden', tabName !== 'notifications');
        }

        if (noticesList) {
            noticesList.classList.toggle('hidden', tabName !== 'notices');
        }

        if (panelActions) {
            panelActions.classList.toggle('hidden', tabName !== 'notifications');
        }
    }

    async function fetchNotifications() {
        try {
            const response = await fetch('/api/notifications?limit=20', {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                return;
            }

            const payload = await response.json();
            alertState.notifications = payload.notifications || [];
            const unreadCount = typeof payload.unread_count === 'number'
                ? payload.unread_count
                : alertState.notifications.filter(function (item) {
                    return !item.is_read;
                }).length;

            setBadge(unreadCount);

            if (alertState.activeTab === 'notifications') {
                renderNotifications();
            }
        } catch (error) {
            // Ignore fetch errors so normal page interactions stay responsive.
        }
    }

    async function fetchNotices() {
        try {
            const response = await fetch('/api/notices?limit=20', {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                return;
            }

            const payload = await response.json();
            alertState.notices = payload.notices || [];

            if (alertState.activeTab === 'notices') {
                renderNotices();
            }
        } catch (error) {
            // Ignore fetch errors so normal page interactions stay responsive.
        }
    }

    async function markNotificationAsRead(notificationId) {
        try {
            const response = await fetch('/api/notifications/read/' + notificationId, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                return;
            }

            const payload = await response.json();
            alertState.notifications = alertState.notifications.map(function (item) {
                if (item.id === notificationId) {
                    return Object.assign({}, item, { is_read: true });
                }
                return item;
            });

            setBadge(payload.unread_count || 0);
            renderNotifications();
        } catch (error) {
            // Ignore mark read errors and keep UI usable.
        }
    }

    async function markAllAsRead() {
        try {
            const response = await fetch('/api/notifications/read-all', {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                return;
            }

            alertState.notifications = alertState.notifications.map(function (item) {
                return Object.assign({}, item, { is_read: true });
            });

            setBadge(0);
            renderNotifications();
        } catch (error) {
            // Ignore mark-all errors and keep UI usable.
        }
    }

    function openNotificationPanel() {
        if (!notificationPanel || !notificationOverlay) {
            return;
        }

        notificationPanel.classList.add('open');
        notificationOverlay.classList.add('active');
        notificationPanel.setAttribute('aria-hidden', 'false');
        updateBodyScroll();
    }

    function closeNotificationPanelFn() {
        if (!notificationPanel || !notificationOverlay) {
            return;
        }

        notificationPanel.classList.remove('open');
        notificationOverlay.classList.remove('active');
        notificationPanel.setAttribute('aria-hidden', 'true');
        updateBodyScroll();
    }

    if (notificationToggle) {
        notificationToggle.addEventListener('click', function (event) {
            event.stopPropagation();

            if (notificationPanel && notificationPanel.classList.contains('open')) {
                closeNotificationPanelFn();
            } else {
                openNotificationPanel();
                fetchNotifications();
                fetchNotices();
            }
        });
    }

    if (closeNotificationPanel) {
        closeNotificationPanel.addEventListener('click', closeNotificationPanelFn);
    }

    if (notificationOverlay) {
        notificationOverlay.addEventListener('click', closeNotificationPanelFn);
    }

    tabButtons.forEach(function (button) {
        button.addEventListener('click', function () {
            const selectedTab = button.dataset.tab;
            setTab(selectedTab);

            if (selectedTab === 'notifications') {
                renderNotifications();
            } else {
                fetchNotices();
            }
        });
    });

    if (notificationsList) {
        notificationsList.addEventListener('click', function (event) {
            const readButton = event.target.closest('.mark-read-btn');
            if (!readButton) {
                return;
            }

            const notificationId = Number(readButton.dataset.id);
            if (!Number.isNaN(notificationId)) {
                markNotificationAsRead(notificationId);
            }
        });
    }

    if (markAllReadBtn) {
        markAllReadBtn.addEventListener('click', markAllAsRead);
    }

    document.addEventListener('click', function (event) {
        if (!notificationPanel || !notificationToggle) {
            return;
        }

        if (!notificationPanel.classList.contains('open')) {
            return;
        }

        if (!notificationPanel.contains(event.target) && !notificationToggle.contains(event.target)) {
            closeNotificationPanelFn();
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            closeNotificationPanelFn();
        }
    });

    setTab('notifications');
    fetchNotifications();

    window.setInterval(function () {
        fetchNotifications();

        if (alertState.activeTab === 'notices' || (notificationPanel && notificationPanel.classList.contains('open'))) {
            fetchNotices();
        }
    }, 30000);
});
