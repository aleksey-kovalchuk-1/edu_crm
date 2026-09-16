import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router";
import { GraduationCap, LogIn, LogOut } from "lucide-react";
import {
  authKeys,
  loginUrl,
  registerUrl,
  useCurrentUser,
  useLogout,
  type Session,
} from "../api/auth";
import { ApiError, errorText } from "../api/client";
import { ErrorAlert } from "../components/QueryState";
import { browser } from "../lib/browser";
import { hasCrmAccess } from "../lib/user";

export const AUTH_ERROR_MESSAGES: Record<string, string> = {
  LOGIN_CANCELLED: "Вход отменён.",
  LOGIN_EXPIRED: "Время на вход истекло. Попробуйте ещё раз.",
  LOGIN_FAILED:
    "Не удалось выполнить вход. Попробуйте ещё раз или обратитесь к администратору.",
  NO_ACCESS:
    "У вашей учётной записи нет доступа к CRM. Обратитесь к администратору.",
  // Set by the interface itself when a fresh login still leaves no session.
  SESSION_NOT_SAVED:
    "Не удалось завершить вход. Проверьте, что браузер разрешает cookie для этого сайта, и попробуйте снова.",
};

const REDIRECT_MARK = "edu-crm:login-redirect-at";
/** A second automatic redirect within this window means login is looping. */
const LOOP_WINDOW_MS = 15_000;
/** After this delay the loading screen offers a manual login button. */
const SLOW_LOADING_MS = 5_000;

function readRedirectMark(): number {
  try {
    return Number(sessionStorage.getItem(REDIRECT_MARK)) || 0;
  } catch {
    return 0;
  }
}
function writeRedirectMark() {
  try {
    sessionStorage.setItem(REDIRECT_MARK, String(Date.now()));
  } catch {
    // Storage unavailable: the loop guard is best-effort.
  }
}
function clearRedirectMark() {
  try {
    sessionStorage.removeItem(REDIRECT_MARK);
  } catch {
    // Storage unavailable.
  }
}

interface SessionContextValue {
  session: Session;
  onLoggedOut: () => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

function useSessionContext() {
  const value = useContext(SessionContext);
  if (!value) throw new Error("Session hooks must be used inside AuthGate");
  return value;
}

/** Current session; only available inside AuthGate. */
export const useSession = () => useSessionContext().session;

/** Logout action for the signed-in interface. */
export function useSignOut() {
  const { onLoggedOut } = useSessionContext();
  return useLogout(onLoggedOut);
}

function AuthScreen({
  title,
  subtitle = "Вход выполняется через корпоративную учётную запись.",
  message,
  children,
}: {
  title: string;
  subtitle?: string;
  message?: string;
  children?: ReactNode;
}) {
  const actions = useRef<HTMLDivElement>(null);
  const [announce, setAnnounce] = useState(false);
  useEffect(() => {
    actions.current?.querySelector("button")?.focus();
    // Insert the message into the live region after mount so it is announced.
    const timer = setTimeout(() => setAnnounce(true), 30);
    return () => clearTimeout(timer);
  }, []);
  return (
    <main className="auth-screen">
      <section className="auth-card">
        <div className="auth-brand">
          <span className="university-icon">
            <GraduationCap size={25} />
          </span>
          <span>
            <strong>образование</strong>
            <small>CRM · ЦИФРОВЫЕ НАВЫКИ</small>
          </span>
        </div>
        <p className="eyebrow">ОБРАЗОВАТЕЛЬНЫЕ ПАРТНЁРСТВА</p>
        <h1>{title}</h1>
        <p className="subtitle">{subtitle}</p>
        <div aria-live="assertive">
          {announce && message && (
            <div className="error" role="alert">
              {message}
            </div>
          )}
        </div>
        <div className="auth-actions" ref={actions}>
          {children}
        </div>
      </section>
    </main>
  );
}

function LoadingScreen({ onLogin }: { onLogin: () => void }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), SLOW_LOADING_MS);
    return () => clearTimeout(timer);
  }, []);
  return (
    <div className="auth-screen">
      <div className="auth-loading">
        <div className="loading" role="status">
          Проверяем вход…
        </div>
        {slow && (
          <div className="auth-actions">
            <button className="primary" onClick={onLogin}>
              <LogIn size={18} />
              Войти
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/** Non-dismissable prompt over the still-mounted page. */
function SessionExpiredDialog({ onLogin }: { onLogin: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const d = dialog.current!;
    if (!d.open) d.showModal();
    button.current?.focus();
    return () => d.close();
  }, []);
  return (
    <dialog
      ref={dialog}
      aria-labelledby="session-expired-title"
      onCancel={(e) => e.preventDefault()}
    >
      <div className="modal">
        <h2 id="session-expired-title">Сессия истекла</h2>
        <p className="subtitle">
          Чтобы продолжить работу, войдите снова. Несохранённые данные на этой
          странице при входе не сохранятся.
        </p>
        <div className="modal-actions">
          <button ref={button} className="primary" onClick={onLogin}>
            Войти снова
          </button>
        </div>
      </div>
    </dialog>
  );
}

/**
 * Renders the app only for an authenticated user with a CRM role.
 * - First visit without a session: redirect to the backend login.
 * - `auth_error` or `logged_out` in the URL: explain and wait for the user.
 * - Session ends mid-use: keep the page mounted and ask to log in again.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const me = useCurrentUser();
  const location = useLocation();
  const navigate = useNavigate();
  const leaving = useRef(false);
  const [loggedOut, setLoggedOut] = useState(false);

  const params = new URLSearchParams(location.search);
  const authError = params.get("auth_error");
  const loggedOutParam = params.has("logged_out");
  params.delete("auth_error");
  params.delete("logged_out");
  const rest = params.toString();
  const nextPath = location.pathname + (rest ? `?${rest}` : "");
  const currentPath = location.pathname + location.search;
  const unauthenticated =
    me.error instanceof ApiError && me.error.status === 401;
  const hasCachedSession = me.data !== undefined;
  const session = loggedOut ? undefined : me.data;

  const onLoggedOut = useCallback(() => {
    clearRedirectMark();
    setLoggedOut(true);
    navigate("/?logged_out=1", { replace: true });
  }, [navigate]);
  const logout = useLogout(onLoggedOut);

  const login = () => {
    leaving.current = true;
    writeRedirectMark();
    if (currentPath !== nextPath) navigate(nextPath, { replace: true });
    browser.assign(loginUrl(nextPath));
  };

  const register = () => {
    leaving.current = true;
    writeRedirectMark();
    if (currentPath !== nextPath) navigate(nextPath, { replace: true });
    browser.assign(registerUrl(nextPath));
  };

  // First visit without a session: go to login automatically (with a loop guard).
  useEffect(() => {
    if (
      loggedOut ||
      hasCachedSession ||
      !unauthenticated ||
      authError ||
      loggedOutParam ||
      leaving.current
    )
      return;
    if (Date.now() - readRedirectMark() < LOOP_WINDOW_MS) {
      const retry = new URLSearchParams(rest);
      retry.set("auth_error", "SESSION_NOT_SAVED");
      navigate(`${location.pathname}?${retry}`, { replace: true });
      return;
    }
    leaving.current = true;
    writeRedirectMark();
    browser.assign(loginUrl(nextPath));
  }, [
    loggedOut,
    hasCachedSession,
    unauthenticated,
    authError,
    loggedOutParam,
    rest,
    nextPath,
    location.pathname,
    navigate,
  ]);

  // Signed in: forget the loop guard and drop stale auth parameters from the URL.
  useEffect(() => {
    if (loggedOut || !session) return;
    clearRedirectMark();
    if (authError || loggedOutParam) navigate(nextPath, { replace: true });
  }, [loggedOut, session, authError, loggedOutParam, nextPath, navigate]);

  // After logout, drop all cached data (including the old session) once the app has unmounted.
  useEffect(() => {
    if (loggedOut) void queryClient.resetQueries();
  }, [loggedOut, queryClient]);

  // Another user signed in (e.g. in another tab): cached data belongs to someone else.
  const userId = me.data?.user.id;
  const lastUserId = useRef(userId);
  useEffect(() => {
    if (userId === undefined) return;
    if (lastUserId.current !== undefined && lastUserId.current !== userId) {
      void queryClient.resetQueries({
        predicate: (query) => query.queryKey[0] !== authKeys.me[0],
      });
    }
    lastUserId.current = userId;
  }, [userId, queryClient]);

  // Back from Keycloak restored from the bfcache: allow redirects again and re-check the session.
  useEffect(() => {
    const onPageShow = (event: PageTransitionEvent) => {
      if (!event.persisted) return;
      leaving.current = false;
      void queryClient.refetchQueries({ queryKey: authKeys.me, exact: true });
    };
    window.addEventListener("pageshow", onPageShow);
    return () => window.removeEventListener("pageshow", onPageShow);
  }, [queryClient]);

  const contextValue = useMemo(
    () => (session ? { session, onLoggedOut } : null),
    [session, onLoggedOut],
  );

  if (loggedOut || (loggedOutParam && !hasCachedSession && unauthenticated)) {
    return (
      <AuthScreen
        key="logged-out"
        title="Вы вышли из системы"
        subtitle="Сеанс работы с CRM завершён."
      >
        <button className="primary" onClick={login}>
          <LogIn size={18} />
          Войти снова
        </button>
        <button type="button" className="secondary" onClick={register}>
          Зарегистрироваться
        </button>
      </AuthScreen>
    );
  }
  if (session && contextValue) {
    if (!hasCrmAccess(session.user.roles)) {
      return (
        <AuthScreen
          key="no-access"
          title="Нет доступа"
          message={AUTH_ERROR_MESSAGES.NO_ACCESS}
        >
          <button
            className="primary"
            onClick={() => logout.mutate()}
            disabled={logout.isPending || logout.isSuccess}
          >
            <LogOut size={18} />
            Выйти
          </button>
          {logout.error && (
            <p className="danger" role="alert">
              {errorText(logout.error)}
            </p>
          )}
        </AuthScreen>
      );
    }
    return (
      <SessionContext.Provider value={contextValue}>
        {children}
        {unauthenticated && <SessionExpiredDialog onLogin={login} />}
      </SessionContext.Provider>
    );
  }
  if (unauthenticated && authError) {
    return (
      <AuthScreen
        key="login"
        title="Вход в CRM"
        message={
          AUTH_ERROR_MESSAGES[authError] ?? AUTH_ERROR_MESSAGES.LOGIN_FAILED
        }
      >
        <button className="primary" onClick={login}>
          <LogIn size={18} />
          Войти через Keycloak
        </button>
        <button type="button" className="secondary" onClick={register}>
          Зарегистрироваться
        </button>
      </AuthScreen>
    );
  }
  if (me.isError && !unauthenticated) {
    return (
      <AuthScreen key="error" title="Вход в CRM">
        <ErrorAlert error={me.error} onRetry={() => void me.refetch()} />
      </AuthScreen>
    );
  }
  return <LoadingScreen onLogin={login} />;
}
