"use client";
import { useState, type ReactNode } from "react";

// Lazily open each page once, then hide rather than unmount it. Local forms,
// file selections, ongoing requests and results survive sidebar navigation.
// This is session UI retention, not durable background-job persistence.
export function RetainedPage({active,children}:{active:boolean;children:ReactNode}) {
 const [opened,setOpened]=useState(active);
 if(active&&!opened)setOpened(true);
 if(!active&&!opened)return null;
 return <section hidden={!active} aria-hidden={!active} style={active?undefined:{display:"none"}}>{children}</section>;
}
