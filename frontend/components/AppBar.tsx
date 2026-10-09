"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { GITHUB_URL, NAME } from "@/shared/brand";
import { Doc, GitHub, Logo, MapMark } from "@/shared/icons";

export function AppBar() {
  const pathname = usePathname();
  return (
    <header className="appbar">
      <Link className="brand" href="/" aria-label={`${NAME} home`}>
        <Logo />
        {NAME}
      </Link>
      <span className="project-badge">Preview</span>
      <nav className="project-nav" aria-label="Main">
        <Link className="nav-link" href="/" aria-current={pathname === "/" ? "page" : undefined}>
          Overview
        </Link>
        <Link className="nav-link" href="/map" aria-current={pathname === "/map" || pathname.startsWith("/substations/") ? "page" : undefined}>
          <MapMark /> Map
        </Link>
        <Link className="nav-link" href="/changelog" aria-current={pathname === "/changelog" ? "page" : undefined}>
          <Doc /> Changelog
        </Link>
        <a className="nav-link" href={GITHUB_URL} target="_blank" rel="noopener noreferrer">
          <GitHub /> GitHub
        </a>
      </nav>
    </header>
  );
}
