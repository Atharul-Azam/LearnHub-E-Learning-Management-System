/* LearnHub - small progressive enhancements only.
 * All business rules, validation and authorization live on the server;
 * every page works with JavaScript disabled except the mobile menu toggle. */
(function () {
  "use strict";

  // Mobile navigation toggle
  var toggle = document.querySelector("[data-nav-toggle]");
  var menu = document.querySelector("[data-nav-menu]");
  if (toggle && menu) {
    toggle.addEventListener("click", function () {
      var open = menu.classList.toggle("hidden") === false;
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  // Copy-to-clipboard share control (falls back to selecting the text).
  document.querySelectorAll("[data-share]").forEach(function (box) {
    var input = box.querySelector("[data-share-input]");
    var button = box.querySelector("[data-copy-button]");
    var status = box.querySelector("[data-copy-status]");
    if (!input || !button) {
      return;
    }
    function say(text) {
      if (status) {
        status.textContent = text;
        window.setTimeout(function () {
          status.textContent = "";
        }, 2500);
      }
    }
    button.addEventListener("click", function () {
      input.select();
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(input.value).then(
          function () {
            say("Link copied");
          },
          function () {
            say("Press Ctrl+C to copy");
          }
        );
      } else {
        var copied = false;
        try {
          copied = document.execCommand("copy");
        } catch (error) {
          copied = false;
        }
        say(copied ? "Link copied" : "Press Ctrl+C to copy");
      }
    });
  });

  // Dropdown menus (<details>): close on Escape or when clicking elsewhere.
  var menus = document.querySelectorAll("details[data-menu]");
  document.addEventListener("click", function (event) {
    menus.forEach(function (menu) {
      if (menu.open && !menu.contains(event.target)) {
        menu.open = false;
      }
    });
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      menus.forEach(function (menu) {
        menu.open = false;
      });
    }
  });

  // Dismissible messages
  document.querySelectorAll("[data-message]").forEach(function (box) {
    var button = box.querySelector("[data-dismiss]");
    if (button) {
      button.addEventListener("click", function () {
        box.remove();
      });
    }
  });

  // Show / hide password
  document.querySelectorAll("[data-toggle-password]").forEach(function (checkbox) {
    checkbox.addEventListener("change", function () {
      var input = document.getElementById(checkbox.getAttribute("data-toggle-password"));
      if (input) {
        input.type = checkbox.checked ? "text" : "password";
      }
    });
  });

  // Genuine processing indicator for upload/save forms: once the browser has
  // started sending the form, disable the submit button to prevent double posts.
  document.querySelectorAll("form[data-loading]").forEach(function (form) {
    form.addEventListener("submit", function () {
      var button = form.querySelector('button[type="submit"]');
      if (button && !button.disabled) {
        button.setAttribute("data-original-label", button.textContent);
        button.textContent = form.getAttribute("data-loading");
        // Disable after the submit event has been dispatched so the POST still contains the form data.
        window.setTimeout(function () {
          button.disabled = true;
        }, 0);
      }
    });
  });

  // Re-enable buttons if the page is restored from the back/forward cache.
  window.addEventListener("pageshow", function (event) {
    if (!event.persisted) {
      return;
    }
    document.querySelectorAll("form[data-loading] button[data-original-label]").forEach(function (button) {
      button.disabled = false;
      button.textContent = button.getAttribute("data-original-label");
    });
  });
})();
