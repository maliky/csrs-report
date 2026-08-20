import {
  Children,
  createContext,
  isValidElement,
  useContext,
  useEffect,
  useMemo,
  useState,
  type AnchorHTMLAttributes,
  type MouseEvent,
  type ReactElement,
  type ReactNode,
} from "react";

export type Location = {
  pathname: string;
  search: string;
  hash: string;
};

type Navigate = (target: string | number) => void;

type RouterState = {
  basename: string;
  location: Location;
  navigate: Navigate;
  params: Record<string, string>;
  outlet: ReactNode;
};

const RouterContext = createContext<RouterState | null>(null);

function normalizedPath(value: string): string {
  const withSlash = value.startsWith("/") ? value : `/${value}`;
  return withSlash.length > 1 ? withSlash.replace(/\/+$/, "") : withSlash;
}

function locationFrom(value: string, basename = ""): Location {
  const parsed = new URL(value, "http://csrs.local");
  const rawPath = normalizedPath(parsed.pathname);
  const base = normalizedPath(basename || "/");
  const pathname =
    base !== "/" && (rawPath === base || rawPath.startsWith(`${base}/`))
      ? normalizedPath(rawPath.slice(base.length) || "/")
      : rawPath;
  return { pathname, search: parsed.search, hash: parsed.hash };
}

function browserLocation(basename: string): Location {
  return locationFrom(
    `${window.location.pathname}${window.location.search}${window.location.hash}`,
    basename,
  );
}

function resolvedTarget(target: string, location: Location): string {
  if (target.startsWith("?")) return `${location.pathname}${target}`;
  if (target.startsWith("#"))
    return `${location.pathname}${location.search}${target}`;
  if (target.startsWith("/")) return target;
  const base = `${location.pathname.replace(/\/$/, "")}/`;
  const resolved = new URL(target, `http://csrs.local${base}`);
  return `${resolved.pathname}${resolved.search}${resolved.hash}`;
}

function externalPath(target: string, basename: string): string {
  const parsed = new URL(target, "http://csrs.local");
  const prefix = basename ? normalizedPath(basename) : "";
  const pathname = normalizedPath(parsed.pathname);
  return `${prefix}${pathname === "/" ? "/" : pathname}${parsed.search}${parsed.hash}`;
}

export function BrowserRouter({
  basename = "",
  children,
}: {
  basename?: string;
  children: ReactNode;
}) {
  const [location, setLocation] = useState(() => browserLocation(basename));

  useEffect(() => {
    const update = () => setLocation(browserLocation(basename));
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, [basename]);

  const navigate: Navigate = (target) => {
    if (typeof target === "number") {
      window.history.go(target);
      return;
    }
    const next = resolvedTarget(target, location);
    window.history.pushState({}, "", externalPath(next, basename));
    setLocation(locationFrom(next));
  };

  return (
    <RouterContext.Provider
      value={{ basename, location, navigate, params: {}, outlet: null }}
    >
      {children}
    </RouterContext.Provider>
  );
}

export function MemoryRouter({
  initialEntries = ["/"],
  children,
}: {
  initialEntries?: string[];
  children: ReactNode;
}) {
  const [entries, setEntries] = useState(() =>
    initialEntries.map((item) => locationFrom(item)),
  );
  const [index, setIndex] = useState(() => Math.max(0, entries.length - 1));
  const location = entries[index] ?? locationFrom("/");
  const navigate: Navigate = (target) => {
    if (typeof target === "number") {
      setIndex((current) =>
        Math.min(Math.max(current + target, 0), entries.length - 1),
      );
      return;
    }
    const next = locationFrom(resolvedTarget(target, location));
    setEntries((current) => [...current.slice(0, index + 1), next]);
    setIndex(index + 1);
  };
  return (
    <RouterContext.Provider
      value={{ basename: "", location, navigate, params: {}, outlet: null }}
    >
      {children}
    </RouterContext.Provider>
  );
}

function useRouter(): RouterState {
  const value = useContext(RouterContext);
  if (!value)
    throw new Error("Ce composant doit être rendu dans un routeur CSRS.");
  return value;
}

export function useLocation(): Location {
  return useRouter().location;
}

export function useNavigate(): Navigate {
  return useRouter().navigate;
}

export function useParams(): Record<string, string> {
  return useRouter().params;
}

type SearchParamsInit =
  string | URLSearchParams | Record<string, string> | Array<[string, string]>;

export function useSearchParams(): [
  URLSearchParams,
  (next: SearchParamsInit) => void,
] {
  const { location, navigate } = useRouter();
  const params = useMemo(
    () => new URLSearchParams(location.search),
    [location.search],
  );
  const setParams = (next: SearchParamsInit) => {
    const query = new URLSearchParams(next);
    navigate(`${location.pathname}${query.size ? `?${query}` : ""}`);
  };
  return [params, setParams];
}

export type LinkProps = Omit<
  AnchorHTMLAttributes<HTMLAnchorElement>,
  "href"
> & { to: string };

export function Link({ to, onClick, children, ...props }: LinkProps) {
  const { basename, location, navigate } = useRouter();
  const target = resolvedTarget(to, location);
  const href = externalPath(target, basename);

  function follow(event: MouseEvent<HTMLAnchorElement>) {
    onClick?.(event);
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      props.target === "_blank"
    )
      return;
    event.preventDefault();
    navigate(target);
  }

  return (
    <a {...props} href={href} onClick={follow}>
      {children}
    </a>
  );
}

export type NavLinkProps = Omit<LinkProps, "className"> & {
  end?: boolean;
  className?: string | ((state: { isActive: boolean }) => string);
};

export function NavLink({ end = false, className, ...props }: NavLinkProps) {
  const location = useLocation();
  const target = resolvedTarget(props.to, location).split(/[?#]/, 1)[0];
  const isActive = end
    ? location.pathname === target
    : location.pathname === target ||
      location.pathname.startsWith(`${target}/`);
  const resolvedClass =
    typeof className === "function" ? className({ isActive }) : className;
  return (
    <Link
      {...props}
      className={resolvedClass}
      aria-current={isActive ? "page" : undefined}
    />
  );
}

type RouteProps = {
  path?: string;
  index?: boolean;
  element: ReactNode;
  children?: ReactNode;
};

export function Route(props: RouteProps): ReactElement | null {
  void props;
  return null;
}

function joinedPattern(parent: string, child: string): string {
  if (child.startsWith("/")) return normalizedPath(child);
  if (parent === "/") return normalizedPath(child);
  return normalizedPath(`${parent}/${child}`);
}

function matchPattern(
  pattern: string,
  pathname: string,
  exact: boolean,
): Record<string, string> | null {
  if (pattern === "*") return {};
  const patternParts = normalizedPath(pattern).split("/").filter(Boolean);
  const pathParts = normalizedPath(pathname).split("/").filter(Boolean);
  if (
    exact
      ? patternParts.length !== pathParts.length
      : patternParts.length > pathParts.length
  )
    return null;
  const params: Record<string, string> = {};
  for (let index = 0; index < patternParts.length; index += 1) {
    const expected = patternParts[index];
    const actual = pathParts[index];
    if (expected.startsWith(":"))
      params[expected.slice(1)] = decodeURIComponent(actual);
    else if (expected !== actual) return null;
  }
  return params;
}

function routeElements(children: ReactNode): ReactElement<RouteProps>[] {
  return Children.toArray(children).filter(
    (child): child is ReactElement<RouteProps> =>
      isValidElement<RouteProps>(child) && child.type === Route,
  );
}

function matchedRoute(
  routes: ReactNode,
  pathname: string,
  parentPattern: string,
  inheritedParams: Record<string, string>,
  state: RouterState,
): ReactNode {
  for (const route of routeElements(routes)) {
    const { path = "", index = false, element, children } = route.props;
    const pattern = index ? parentPattern : joinedPattern(parentPattern, path);
    const ownParams = matchPattern(pattern, pathname, !children);
    if (ownParams === null) continue;
    const params = { ...inheritedParams, ...ownParams };
    let outlet: ReactNode = null;
    if (children) {
      outlet = matchedRoute(children, pathname, pattern, params, state);
      const exactParent = matchPattern(pattern, pathname, true) !== null;
      if (outlet === null && !exactParent) continue;
    }
    return (
      <RouterContext.Provider value={{ ...state, params, outlet }}>
        {element}
      </RouterContext.Provider>
    );
  }
  return null;
}

export function Routes({ children }: { children: ReactNode }) {
  const state = useRouter();
  return matchedRoute(children, state.location.pathname, "/", {}, state);
}

export function Outlet({ context }: { context?: unknown }) {
  void context;
  return <>{useRouter().outlet}</>;
}
