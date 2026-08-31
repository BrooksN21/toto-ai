from __future__ import annotations

import base64
import copy
import csv
import hashlib
import io
import json
import zlib
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

import toto_ai.operations.post_draw_attribution as attribution_module
from toto_ai.cli import app
from toto_ai.operations.post_draw_attribution import (
    ANALYSIS_ONLY_LABEL,
    ATTRIBUTION_COMPLETE,
    PENDING_RESULTS,
    AttributionIdentity,
    AttributionIntegrityError,
    attribute_post_draw,
    build_post_draw_attribution_report,
    generate_post_draw_attribution_reports,
    write_post_draw_attribution_reports,
)

_ROOT = Path(__file__).resolve().parents[1]
_RUNTIME_4991 = (
    _ROOT
    / "reports/rehearsal/evening-4991-20260830T130000Z-recovery-20260830T1538"
    / "attempts/final-01-20260830T123821298809Z-be16c5f9"
)
_PACKAGE_SHA256 = "76bc5bf7f7d6596d810d837d304d7477801de8b111296377242f6866efc8c171"
_ARCHIVE_SHA256 = "d97fd18541f5e4e90d079e1483befb7bd3b96cc8f6900932cd51b5cffc27a430"
_FINAL_INPUT_FILE_SHA256 = (
    "74e23e1fbc4bdd3bb1e30e3c1d366a60a20f06fb6d106e3b7f73d2278a99e813"
)
_RESULT_SHA256 = "20df04b5ff69dc495be082e1952cac86a0c81e4e77b80cbf47aaf90a727448b2"
_VOID_SOURCE = "https://example.test/reviewed-void"
_PACKAGE_B85 = (
    "c-m!}*^Xqn4MgAdE$N2#<xlRLVHg8H7??4}%lG>Psme;Jx(D4oQOUZx5*ZPs>d(LZ{?FIn|M"
    ">5}{`md%k3awT_rL%8+y7p_|MnmL3h9-;e`WrArC+($l}4JW<k(kjulNH>A$wrX9+(x_*O;x"
    "wR_my%l}_Ldl~6qJc|7n@U>Ymtk!t1797`hbhC+SqCw;`V-23Wn^%3ieO>s9An#bkm;|<$Le"
    "Uv#z=T&Ob8(vUdp?lzyKHjjT5?g6~tyy9j3cR4&!?3_7J)eOqM!wwHin-F73Ou1P!}P$MKDV"
    "a#JQH7Dd6k$Ictb5L4}9{+JJzbbYIUy8hw~uthDu2Bm6LDj$6Cwit2Fi^H<qQy3+g?j<dOOF"
    "nS-~<V=S^{P76E{PA2fdY<Y7WNY5*dS|&M?R?9k&6G|hb;*rPxl*)-u{+Ki7YHK|Z&LyPkfz"
    "M~Mjvhx$WM?WQcUH3AP#`n1rNC#>)z&*-O)Re{tF^Hg#Kv}y%%4fn__b1;+RD^t(OX_n4QY7"
    "fbChI?9D&}QA{;}BenFAdPDMT`eU=vIRaz^trop$jjJ=_d*6XoF9yK{*jiu$h+Nw3_NG>SNk"
    "mJjr_n8HSii)#LvaO9#ik-;`)sT}%=FiMaBd*yvgIG&Xr5O*LPz!wWc~{BTY9pIa^Ws0=u3D"
    "MgP%R-B4}Cs!FT)soaj`mTF)8$ha>&&ppZu8#dDL3_<hQ<i)QesaIh2incDlcpOYy-{z4p;t"
    "jLM-4ntg<96!fHnyGpKPc<0>W%*`|Yg4o^Rkw?bEZtP%>D#Zo?DDs5j3fV~L$p?E?I4;#WN?"
    "aBG*Na||Ues7<=k3>O`BYh}Qi?DKo1+uGpc+c_$U_tOreid?nAcKuX^T#1jueW~P<p@UuFz!"
    "*%XQVXR<;T~pwvUjUM)wRB~?aBgZJhUQJZ@~eTHH@^yGv3W`P(-ijiDH@$}3KN-Gp2qUX&gu"
    "9~Po%&B(Nk-gOB-Vj^VUcS&nR7&k)^Oy>2%-M+ggxH~Ok#E*aI}$~PSy^N0!zuoRc;>Lk=TJ"
    "a6PD*Jfk!KWbUQipMOe2(hyk~=@GL%Dk<PoP*;f8PrPDRh54v<DMPR2=;V!U}nB~+8Ll#e8;"
    "D99XZviX^hSteW%k;zwk<Pf>S_eX;$$+QLgf@-Mdg1!}Lm)YX{+Jfj*jLXXGfaVO<Y*2oV9M"
    "XZ+!cI`gWw|^YNMy0qU-MAxmT(ZHi?plEZjmRHN2n%d={cQHpJFUAWJ#@??jA^}-NoVg%sgC"
    "Rmu%q(hgPT)Iib8l9sZ7|)r&on+YOOq7cKIFv{YBJ=j2Qr-DuQ9fu5)3>;?6~L)T9CLwLy(U"
    "Wy&eY`zuB1yP(Wdb%I-ncD0T&BCBbLd=<-P@JKqT_}eN_HMbNhooitc|m%nCr~;J29+4GqLD"
    "Me1i5~m5L?uW^YkG|cn}VoZ$1$0YR>(FY75OXC>=H`uQf1Ce6mdrUrBpGlhrmqmSb-@HOK;|"
    "l|(sn+A~imw0>^T7L_im7TJ&*<LD+T2LzKe&!K#|p^8AaEH}Zk+zlO&4rOj-I2PNfK@<zOPi"
    "~tVx}h4{7Y7~6fJS1OdTUS)IcIr$LM`-oN}w}lM`hs-_GGX`W6TRGp>G{Kj8tEf-&Ji1O+xd"
    "2>V$~QryALDvZhW~g6mdAMse*06&jr4nsPZ4ItqMK!?LluY|i9_5YJw>V>~(z%w!o8iN(~8X"
    "2$q}Snjq%r+edNaQYM$MkbpxxgnIScMm=7&?wbxFgrOm+g?!U<0M;`U2>Cc$j||tWzEV3bq;"
    "iH&istTNT>%YCH5SbneiK9v1=d8XA)I$4RQ&(a1%O~8ww-38Xabw>dQ@*0O6sdv5dc<FkHq?"
    "xu&jY6lf1H&sa7)&I{r=M?QVAb9~34$#0F-(OQLG5Dma6XIt)hD=(SV(^O@uZS4h>FsfJfX*"
    "6NTs8Xbp?j@ViydZYSX(%6b3oA~1$b!lvmd`T&gbJ(eCxPuo86rm}5lrgBXy`y1P3st^{c;-"
    "OF-QVFYu2^g{$CKMGClI-X*K@5N)e&g>bB&Bh+Jpm;4}n>V?vjVC_8E6fD_UjA)X$=UvntIa"
    ";GrXay`1C9Omxoj|QnwxgFA=t!}vu)1wO_@}eO-PW%9^KN2f<m`xilX!J0P=j~A`usDa!PGV"
    "mWP3r_Nh-cQ<H-EhqJ4v-LT(q22l?dU25Txmy)j8bZFGM6$`4Om_svJnHVUEr4N2TC{TcW+7"
    "95o=b>O7#vBiGkhXtw~*EC0&)0lwbp*+@17JN<ydioUb^k*wLcR{M`<E;Qpgn~<GQ9RZ$rY<"
    "Tfl=bGJJ<W#78nxKw{w&v)DcqXTr-(8iM(;N+UD~nTMRx-vM%?SluYyPG$eGjDp&FRty`^b?"
    "jRT^AS35&y&?|*h-vp*^^)M{0;Ua5P99Z1Y!Nl~<+d6Rs86}q;rPGnF|Ee<8;4=Aku@|gUU2"
    "_p9-yB(vZa*&RA<c5eG-a8uYX?t{*xNZ87K|xXfUAg%K3iJ^!Uut&kY{bzC$IXX|t;Sl73xd"
    "M}`|Ul7ZxCE<1GlDDaafPqSG9@T2?ZL^JvY-Y>&jTIe1L3dGloo-7zaXJ+GDe~Z?hf+yVUUl"
    "6fqiLR{DfAsf&4=FH=B0*Ct96E0HE%l-7S)O<zzWRNb|X@i7+SPgaXo;kjWA99Ng-+(?kgc|"
    "6k}&jQ=pV!aF=0^Ok}*4Cbod@UUR$`<x~`4THJL_M<~wJs%&mDmAk3`(_|aDI7BI~MA9YA(#"
    "ylcXkq7u2;$aEZO@<Gtse5poFhnaw0*+V*}TV<{3*dHgt?IUiD<o_%O6w}wVQGL%0cBE>?Mw"
    "myY0N}wiC^g#m`F+xW0H<Uw4aSOJm{$mB&<$5TP1|gF$W>GJQGu5#8@zb%RarvAbyS;Esm}d"
    "-|vE~7Fjz-D43&vB}(m@i7q$4Is{1k285RqliCXE2~RGUX(4oNsnWvqBhn@63HLhI}8zN`R}"
    "$%DpLe1fE%Zl!LBG)$X~lKaLzYu2#K6-YCCE7J=iQgmd*>09jUomoQ;vIfWRgYgT(grRS*w7"
    "sA2v*kX&IC-S6%KexgzyA+0n?3*bm#DX$O5wb9Nz1m4;v7rLqfT|NHVHeSt_Ra9y~nsVz%xr"
    "ugMoh0U*p}Za4txpIc^Cy=c#JfMn#)DEP66DrAT5fXzB(bZ7TFfW($=?oN8`jp#yYJbwc#pI"
    "u7@$UUv5Xzwq7Bnq)`;Ss6CkJs~2?%b)dZ;r9y<IwG>YuHJL^$~mE|hbo=69_Fv(p{8i*$?~"
    "W{sEOhYQLnk}+Y&4Gy}`pqES;2V-|2KfMZ45rUTt~ToGJ&Cs5undSQp7VZT@&dA=&iUMR60N"
    "J_cVRNGL?3wO0pnA-E&h)XCdZU;nad9bz92AZt`(#d;vbt=IcuW*zorTSq^2?z5BZe%W?F>`"
    "+17Oe^wNto6S*=?Q_ck%*wRzn{p|MO4w{=gtHF8x|!`t7Uk_Wl)@2{{@9)v*SH8^nxW)21*Z"
    "`q#aEi2loRavh2yI+ZE6HvXZR3mPPAn{`x?&4yDwu?$@2ev%4PjmVT3N4vUh!>-mJD?#<fkd"
    "A2q8owE6Q(flE@uBG17=IaNPbTw4mBzfw8iB!>5u8bT1po!?V;sa`Wtg+IwJzaYCZ3`TvJC4"
    "$0%ic6y5Rqb}$9$Pj0gd#N?k!i*{nx6!xpO)oA|WIZw$XzXt6dZ8(wY`$=}NfxHSr0NNHxA5"
    "=alUJ)$|RT?z%?O&1bRk!VM`j8UJqYp|p^boDE~$s1S^Kw^r?jcvX#%%|Sl9dGc$B$v2KP97"
    "S^ozlJy<Nn@2$+IIQ9OFgL{gLV+XMJr*GjuRrXzD(8fZVfE5S%xFq895tm+T8Snh-?xm3w``"
    "#B`bN=(KWwM)Q62VZb%R9ySFr(|0Sx;X2l$1flX`(ctOgfs`fj7HN)H6iF3s6YzA9t^WYoO("
    "ai6uw;!(c!i$gOp`LW#gk6wyv96cT3fzFWE^4mMI&COlt2L%K#8X>*?T*d)-rg1Sg&V?@>$b"
    "z&#0zS=a!$L>U8c67Y~*>?L?2yp>wH7(uuYTmo^xr3t!x@ZkWkL5OH^t74~WQO79cwbKi;-c"
    "&aiD78ph6OL#GRh3av&iKI(clbyFE}X*5;Qz-8;bAtI%1F2avjkFt;irzB-vBuLuv6A8Me__"
    "{0f37cOuCaEqigTAubP0s~M#G4Yya^XvBjFRv(m1D0yCO1ktA#Lt5=dk6}YJ72ibf7R#u6hh"
    "|I)6X`tM%Fr)V-ZWM*WyWp{AOCgadM)KOiF0_cM3o`~_uU$fK@1=+xS4+z4^mclKkg6Y|j&O"
    "XKVzXk9OjA5c(_op-DF5!tGKT!05u^)O437er+Je#_?_NxCc)iFBJ}%T(kA5!t@q@*SxOBgb"
    "Z+gfKIaH$-Ire$V&*Q1+#&{H@pJBjX1YAjI`v?yk01$CoSwP%bQL^!I8v67=&SK3wzO%bwYO"
    "$q~bn_Ok*~`d9q{h3Sc~W37*}Q2IeOkP7Z(dQ;?yg#QCN;kAG"
)
_ARCHIVE_B85 = (
    "c-n1KU2ohV5Pa{?@N=Al1s1s9(Z1xxf@R5BO|XT1S4CC-d)NI)q9~RntnuzJGYdb5)af$ccz"
    "RB4uDtEjc1hrHI1d;!1FMj=(Wa_^WFa`sm9jOi#t3L5VTH<t6jkGlWgAkeAyM>pxcg6DrnCz"
    "oD8NyL(WtK)&Q_g`xi?ywpdO@_Qd`<g>1kRMeNT`4ro_77U9C08hzP|dM><krjLAXJ+Pciv8"
    "*K}P$OaI6RkB%0T7wPYU|%+oU}I3n_jO&`Buf)aBi;?Aryp~BoaQ0`sG#4Vc74v=kKQOKxAK"
    "`CJS!#d;iJw?Jj`vq?h~bTzxL1ln{WnwkI_e?KlZ&kH^h#jL{3phAWI3+xs-KO5G8T%&{}P4"
    "VqMv$VgZamkO?%ol7)BeOHO%yn)jEF?3PqjM46d1YDF2y6r(9rr%HtqJOi4H-ew5VAVvsMgf"
    "-floicyfZ`@KN7QVIflzE@}wKa+CZrJF;&uO}G-{z$aXAo$)c9OD}owqk79y7UIef0%h#1gb"
    "B!T4g7E#7(`lrAhMQRW%Zcn=mT21H3FkoJ0bC0^5h5yI2AO*TDA`rCzX{j@LpGN$>|d0qOx$"
    "$H_`xAb&k(JylzkNJ+rh*UTRWRyG)V`mbB{pH;sXTmA%J3p_&^Ji+Kdfy2qfXEC%#fLGoMv}"
    "{N`gf@BX}cX__w-#7GwRou-vaFlBm"
)
_FINAL_INPUT_B85 = (
    "c-qyO+m72d5J2Di6$?GD4RUz*TmPX?X$ym*sH_@Wc5OLD5ai!WUA#LaC9eYqMQSXx7R}3O4r"
    "e$s`dZko^ZR4BZK`5Z)J<!5D?(R5KoZT!ZxomY3Px*UKCDVlr4zL&o(pG>-R0z~t?k0VzW<8"
    "o)i7ei^aki!8f6&$5c*c$R=cM4Nk_IJB>as%I@|2FNBd=Wu+{ebVnN8zU4m0KNFYE}%oEFNC"
    ">>C%xN)xZS~ydcl5$dOp;RdiFj-gJFiBa>J@iwb>_1KWad<!qMANsX_OdVisn~F1LhH16vH4"
    "n5wzK_z-&S)^C`ZB9Wcc**`_I1Z&c){UuZ4TD`(txx&o9j}jQit4I3@j+Rl}7H*K)Y({>tn1"
    ")6lCP?#8}ixVoXmy|r+%8oHw4(}W~QF+8FsjOyp2wR?YE9{1+MG&HOTgz|A=nk_tt%3-(;Bb"
    "Y~hcrnhu^=+|fFT34yaX3}ICdqU0_vO&}bFaPf)3(=iv4J2@xCuJn(qhB->m7u<Ue?2DKXqk"
    "mer=e#!`d*^0)30<aUBl3>!9oHbp?s;`!(3N=i=ngmt9XX2!D2mlb^nJ_S6lC`v>{<{Br;_5"
    "kR104<rP~QzC%`?t>x22p$Q~$I)Y7w}_O^BQ+Q)XBa7@NP8YJQkEcPLkmLM&mSS>2~zbaQkH"
    "4ZWm=B$Ql!D00!_EY3|AnrVG=YWL$jcjCfQiTQX@%Aw8iWw&l6d;P?*Q5Zs0TtPQg>0kmFP_"
    "P9EbFB*qEyQJfm7uYL#Q2#Gx1VTnLvVu<*(404R4!<^<Czx!y#(e`aN4(+LtB(Ea}4Jq%)O;"
    "h}ci{RNTcm|PcR*`F_5%}PUO$uJh6g-u&YZi$ei^Pt}&k7#qT(C$@ZbD8XTzE4eT+#Nh$frz"
    "A*pjiw_lr#VJW~=e6%kXB7&BzPS@HC^)$bg)`e$bP1ehv|&Do;KIhvf_HovQpqH#WR|I0pD%"
    "wwYwHW^`q1RKesB$Y);hTS&B1RJOygDrPf5io2?)8RJ#{`4y*#bZ(xnzha~9`QmBb~@CTO-S"
    "Cu;+9(sEJWrOGq0#`MmK^cC?2&SAn1&t`6=-|0qb4fQpDa8A8XjfRS_qSe?fd5J~~lUHb$(|"
    "cZDJzyxGViYIO%{PH#rCB#&fG%9_Wld(*|Nd6Jv}Jj$9QipWoLx#%rp2T3tV8H41bL80w3sU"
    "KM`lMz+yq$Lt$8H~OoYveitlVl6>9eZLwm5x>H+8lCM*bMBe8N4air3m;;V6v!a^WDLJ=Imt"
    "V>_DUzkkV0!1+X6-FDwLSllJ4|N2T6wI!^RF1s;VDdM1Cv#gZxN$A?>u<Mk+uqj|w)NDu(B)"
    "WD?aCaabc_PdHOCZf#J6i=m;c^+OsOqnG%D1NY?`|l{n)fWnBmd|0K`V!mfAOlBX%5~f-jVh"
    "xfm|@YEDKFGzWJDP-Wu8*jET$adl#Fr$IXTQAIn2bvkQb6_TqL;>TRwuFk;RB}!oK9F%gC%p"
    "Q%13HL^n!T^14%AY+XJ!Dcn<<Baxw#v@{1<K%+Bvemnik0vh%|-UD<oKb#I)f<qxall;4kpm"
    "=lPGe!2vt1VMzk0<#wJG8Y*4PCvHEv5xn`e;Z6X_0d-m;zjMt-m)dVM!6ELLRx!Y7G8$;-r*"
    "wHQKyNw=~BxO@2ob0@2~jW1Hn`l9b`-T0oM8h%Dnwa7GzuzlgXS=bw{)$9HLeS@-F9==!i@_"
    "`E8-w7ahK-D+=}wpT~`u5CZQF&nirh;qK{drc4~xEWUME}=tVUDtf}MUd~aKb^xS3T<>v`iA"
    "4qw&R;i%Uwk)2#WB=0`0@?<LOY^ve`A=mu=G?FWuW~MeayV`WJ}aQAvp_!Lf=_r)xo~8Y-<k"
    "NLEV4OVEZ%X+VcgvNpUf1!04JUi{u}UquQJb#CqP{Bl6+Fz1CczIM(~1CBc@r4Y8HhJdM=P("
    "p_7!)xnl?YXUjQLxZ7yyJADD#JQK_aA+?t(*3vKOIj^+w-ZFw2BMod?|&d3TkDorQx{^&>*<"
    "8yp)=#x~vIMrNdg1=~8LOJ@KNihIGxoe+7C74{&NK|0?r<_?LeHF{j$H"
)
_RESULT_B85 = (
    "c-pPg%?iRW3<vO689DFJr2FiX2qHsV55jQJc3#AHw;oIfcCeNmo5GKf<bQsFe(HxC?jtDdgv"
    "73d*^JtN5+xXIm&t*G6Z{^7byv4oU-R#Idg{@C+1qTiFJYkygm?L;_N?Mc#r>*?s3cgWbX9J"
    "t$g0d!V-p}^wOXmPPZeIJm?~MVkJ}bitTySr;#RLUtL=evZCLFNyn&Y0K3%0PHDn7#-e9X3y"
    "9yVkUjc3GONMkIrFZ*fWsD8+LYbF@*d54_FRb!b=Gn^!6g!fp"
)


@dataclass(frozen=True)
class AttributionFixture:
    identity: AttributionIdentity
    coupons: list[str]
    events: list[dict[str, object]]
    package_payload: bytes
    final_input_payload: bytes
    settled_result_payload: bytes


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _final_input_canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _unpack(value: str) -> bytes:
    return zlib.decompress(base64.b85decode(value.encode("ascii")))


def _actual_or_embedded(path: Path, embedded: str, expected_sha256: str) -> bytes:
    value = path.read_bytes() if path.is_file() else _unpack(embedded)
    assert _sha256(value) == expected_sha256
    return value


def _parse_coupons(package_payload: bytes) -> list[str]:
    rows = list(csv.DictReader(io.StringIO(package_payload.decode("utf-8"))))
    return [str(row["coupon"]) for row in rows]


def _fixture_4991() -> AttributionFixture:
    package_payload = _actual_or_embedded(
        _RUNTIME_4991 / "package.csv",
        _PACKAGE_B85,
        _PACKAGE_SHA256,
    )
    archive_payload = _actual_or_embedded(
        _RUNTIME_4991 / "package-archive.json",
        _ARCHIVE_B85,
        _ARCHIVE_SHA256,
    )
    final_input_payload = _actual_or_embedded(
        _RUNTIME_4991 / "final-input.json",
        _FINAL_INPUT_B85,
        _FINAL_INPUT_FILE_SHA256,
    )
    settled_result_payload = _unpack(_RESULT_B85)
    assert _sha256(settled_result_payload) == _RESULT_SHA256

    archive = json.loads(archive_payload)
    unsigned_archive = dict(archive)
    declared_archive_sha = unsigned_archive.pop("archive_manifest_sha256")
    assert _sha256(_canonical_bytes(unsigned_archive)) == declared_archive_sha
    assert archive["source_bytes_sha256"] == _sha256(package_payload)

    coupons = _parse_coupons(package_payload)
    assert len(coupons) == archive["coupon_count"] == 166
    assert archive["canonical_package_sha256"] == _sha256(
        ",".join(coupons).encode("utf-8")
    )

    final_input = json.loads(final_input_payload)
    unsigned_final_input = dict(final_input)
    declared_final_input_sha = unsigned_final_input.pop("snapshot_sha256")
    assert (
        _sha256(_final_input_canonical_bytes(unsigned_final_input))
        == declared_final_input_sha
    )
    assert archive["final_input_sha256"] == declared_final_input_sha

    settled = json.loads(settled_result_payload)
    assert _sha256(_canonical_bytes(settled)) == _RESULT_SHA256
    frozen = final_input["payload"]["data"]["events"]
    assert [row["order"] for row in frozen] == list(range(15))
    assert [row["order"] for row in settled] == list(range(15))

    events: list[dict[str, object]] = []
    for position, (frozen_event, settled_event) in enumerate(
        zip(frozen, settled, strict=True),
        start=1,
    ):
        home, away = frozen_event["name"].split(" — ", 1)
        quotes = frozen_event["quotes"]
        events.append(
            {
                "position": position,
                "event_id": frozen_event["id"],
                "home_team": home,
                "away_team": away,
                "score": settled_event["score"],
                "result": settled_event["result"],
                "bk": {
                    "1": quotes["bk_win_1"],
                    "X": quotes["bk_draw"],
                    "2": quotes["bk_win_2"],
                },
                "pool": {
                    "1": quotes["pool_win_1"],
                    "X": quotes["pool_draw"],
                    "2": quotes["pool_win_2"],
                },
            }
        )

    identity = AttributionIdentity(
        drawing_id=archive["drawing_id"],
        drawing_number=archive["drawing_number"],
        plan_id=final_input["plan_id"],
        package_id=archive["archive_manifest_sha256"],
        final_input_sha256=archive["final_input_sha256"],
        package_sha256=archive["canonical_package_sha256"],
        result_sha256=_RESULT_SHA256,
    )
    return AttributionFixture(
        identity=identity,
        coupons=coupons,
        events=events,
        package_payload=package_payload,
        final_input_payload=final_input_payload,
        settled_result_payload=settled_result_payload,
    )


def _synthetic_fixture(
    coupons: list[str],
    *,
    results: tuple[str, ...] = ("1", "1", "1"),
) -> AttributionFixture:
    drawing_id = 77
    drawing_number = 88
    plan_id = "synthetic-plan"
    package_id = "synthetic-package"
    frozen_events: list[dict[str, object]] = []
    settled_events: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    for order, actual in enumerate(results):
        event_id = 9000 + order
        frozen_events.append(
            {
                "id": event_id,
                "order": order,
                "name": f"Home {order + 1} — Away {order + 1}",
                "quotes": {
                    "bk_win_1": 50,
                    "bk_draw": 30,
                    "bk_win_2": 20,
                    "pool_win_1": 45,
                    "pool_draw": 30,
                    "pool_win_2": 25,
                },
            }
        )
        score = "" if actual == "VOID" else "1 : 0"
        settled = {
            "event_id": event_id,
            "order": order,
            "result": actual,
            "result_status": "void" if actual == "VOID" else "resolved",
            "score": score,
        }
        if actual == "VOID":
            settled["void_source"] = _VOID_SOURCE
        settled_events.append(settled)
        event: dict[str, object] = {
            "position": order + 1,
            "event_id": event_id,
            "home_team": f"Home {order + 1}",
            "away_team": f"Away {order + 1}",
            "score": score,
            "result": actual,
        }
        if actual != "VOID":
            event["bk"] = {"1": 50, "X": 30, "2": 20}
            event["pool"] = {"1": 45, "X": 30, "2": 25}
        events.append(event)

    frozen_payload = {
        "data": {
            "id": drawing_id,
            "number": drawing_number,
            "events": frozen_events,
        }
    }
    unsigned_final = {
        "schema_version": 1,
        "plan_id": plan_id,
        "attempt_id": "synthetic-attempt",
        "drawing_id": drawing_id,
        "drawing_number": drawing_number,
        "deadline": "2026-01-01T00:00:00Z",
        "captured_at": "2025-12-31T23:00:00Z",
        "target_fingerprint": "f" * 64,
        "detail_payload_sha256": _sha256(_final_input_canonical_bytes(frozen_payload)),
        "probability_input_sha256": "e" * 64,
        "timing_override_sha256": None,
        "payload": frozen_payload,
    }
    final_input_sha = _sha256(_final_input_canonical_bytes(unsigned_final))
    final_input_payload = (
        _final_input_canonical_bytes(
            {**unsigned_final, "snapshot_sha256": final_input_sha}
        )
        + b"\n"
    )
    settled_result_payload = _canonical_bytes(settled_events)
    package_payload = (
        "rank,coupon\n"
        + "".join(f"{rank},{coupon}\n" for rank, coupon in enumerate(coupons, 1))
    ).encode("utf-8")
    identity = AttributionIdentity(
        drawing_id=drawing_id,
        drawing_number=drawing_number,
        plan_id=plan_id,
        package_id=package_id,
        final_input_sha256=final_input_sha,
        package_sha256=_sha256(",".join(coupons).encode("utf-8")),
        result_sha256=_sha256(settled_result_payload),
    )
    return AttributionFixture(
        identity=identity,
        coupons=coupons,
        events=events,
        package_payload=package_payload,
        final_input_payload=final_input_payload,
        settled_result_payload=settled_result_payload,
    )


def _artifact_payloads(
    fixture: AttributionFixture,
    *,
    settled_events: list[dict[str, object]] | None = None,
    package_dir: Path | None = None,
) -> tuple[bytes, bytes, bytes]:
    root = (package_dir or Path("/scheduler/run")).resolve()
    unsigned_archive = {
        "schema_version": 2,
        "provenance": "pre_bet_runner",
        "drawing_id": fixture.identity.drawing_id,
        "drawing_number": fixture.identity.drawing_number,
        "ended_at": "2026-01-01T01:00:00Z",
        "archived_at": "2026-01-01T01:05:00Z",
        "stake": 30,
        "coupon_count": len(fixture.coupons),
        "cost": 30 * len(fixture.coupons),
        "source_path": str(root / "package.csv"),
        "source_bytes_sha256": _sha256(fixture.package_payload),
        "canonical_package_sha256": fixture.identity.package_sha256,
        "final_input_sha256": fixture.identity.final_input_sha256,
        "probability_input_sha256": "e" * 64,
        "final_input_captured_at": "2025-12-31T23:00:00Z",
    }
    manifest_sha256 = _sha256(_final_input_canonical_bytes(unsigned_archive))
    archive_payload = _final_input_canonical_bytes(
        {
            **unsigned_archive,
            "archive_manifest_sha256": manifest_sha256,
        }
    )
    events = (
        copy.deepcopy(json.loads(fixture.settled_result_payload))
        if settled_events is None
        else copy.deepcopy(settled_events)
    )
    raw_events = []
    for event in events:
        raw = {key: value for key, value in event.items() if key != "event_id"}
        raw["id"] = event["event_id"]
        raw_events.append(raw)
    settled_payload = _canonical_bytes(
        {
            "data": {
                "id": fixture.identity.drawing_id,
                "number": fixture.identity.drawing_number,
                "status": "finished",
                "events": raw_events,
            }
        }
    )
    final_input = json.loads(fixture.final_input_payload)
    unsigned_operator = {
        "schema_version": 3,
        "plan_id": final_input["plan_id"],
        "drawing": fixture.identity.drawing_number,
        "drawing_id": fixture.identity.drawing_id,
        "run_id": root.name,
        "operator_status": "FINAL_FRESH",
        "decision": "PLAY",
        "provenance": "FINAL_FRESH",
        "source_package_path": str(root / "package.csv"),
        "source_package_sha256": _sha256(fixture.package_payload),
        "archive_manifest_path": str(root / "package-archive.json"),
        "archive_manifest_sha256": manifest_sha256,
        "coupon_path": str(root / "baltbet-upload.txt"),
        "status_path": str(root / "status.json"),
        "marker_path": str(root / ".bet-ready"),
        "package_sha256": "a" * 64,
        "stake": 30,
        "requested_bank": 30 * len(fixture.coupons),
        "effective_bank": 30 * len(fixture.coupons),
        "selected_count": len(fixture.coupons),
        "selected_cost": 30 * len(fixture.coupons),
        "published_at": "2025-12-31T23:30:00Z",
        "expires_at": "2025-12-31T23:50:00Z",
        "completed_at": "2025-12-31T23:31:00Z",
        "automatic_wagering": False,
        "actionable": True,
        "release_mode": "STANDARD",
        "release_authorization_path": None,
        "release_authorization_sha256": None,
        "risk_acknowledged": False,
        "profitability_proven": False,
        "reason": "fresh scheduler-owned operator package",
    }
    operator_payload = _canonical_bytes(
        {
            **unsigned_operator,
            "record_sha256": _sha256(_canonical_bytes(unsigned_operator)),
        }
    )
    return archive_payload, settled_payload, operator_payload


def _updated_operator_payload(payload: bytes, **changes: object) -> bytes:
    document = json.loads(payload)
    document.update(changes)
    document.pop("record_sha256", None)
    return _canonical_bytes(
        {
            **document,
            "record_sha256": _sha256(_canonical_bytes(document)),
        }
    )


def _write_artifact_files(
    tmp_path: Path,
    fixture: AttributionFixture,
    *,
    settled_events: list[dict[str, object]] | None = None,
) -> tuple[Path, Path, Path, Path]:
    package_dir = tmp_path / "run-1"
    package_dir.mkdir()
    archive_payload, settled_payload, operator_payload = _artifact_payloads(
        fixture,
        settled_events=settled_events,
        package_dir=package_dir,
    )
    (package_dir / "package.csv").write_bytes(fixture.package_payload)
    (package_dir / "package-archive.json").write_bytes(archive_payload)
    (package_dir / "final-input.json").write_bytes(fixture.final_input_payload)
    settled_path = tmp_path / "settled-drawing.json"
    settled_path.write_bytes(settled_payload)
    operator_path = tmp_path / "operator-result.json"
    operator_path.write_bytes(operator_payload)
    return package_dir, operator_path, settled_path, tmp_path / "reports"


def _attribute(
    fixture: AttributionFixture,
    *,
    expected: AttributionIdentity | None = None,
    observed: AttributionIdentity | None = None,
) -> dict[str, object]:
    return attribute_post_draw(
        expected_identity=expected or fixture.identity,
        observed_identity=observed or fixture.identity,
        coupons=fixture.coupons,
        events=fixture.events,
        package_payload=fixture.package_payload,
        final_input_payload=fixture.final_input_payload,
        settled_result_payload=fixture.settled_result_payload,
    )


def test_actual_4991_archive_matches_required_package_facts() -> None:
    fixture = _fixture_4991()

    result = _attribute(fixture)

    assert result["best_hits"] == 11
    assert result["missed_positions"] == [1, 6, 12, 15]
    rows = {row["position"]: row for row in result["events"]}
    assert rows[1]["exposures"] == {"1": 57, "X": 43, "2": 66}
    assert rows[6]["exposures"] == {"1": 53, "X": 48, "2": 65}
    assert rows[12]["exposures"] == {"1": 34, "X": 18, "2": 114}
    assert rows[15]["exposures"] == {"1": 17, "X": 34, "2": 115}
    assert result["all_missed_joint_coverage"] == 0
    assert result["at_least_n_missed_coverage"]["3"] == 3
    assert result["at_least_n_missed_coverage"]["2"] == 29


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("drawing_id", 999),
        ("drawing_number", 9999),
        ("plan_id", "other-plan"),
        ("package_id", "other-package"),
        ("final_input_sha256", "d" * 64),
        ("package_sha256", "d" * 64),
        ("result_sha256", "d" * 64),
    ],
)
def test_identity_and_hash_mismatch_fail_closed(field: str, value: object) -> None:
    fixture = _fixture_4991()
    observed = replace(fixture.identity, **{field: value})

    with pytest.raises(AttributionIntegrityError, match="immutable identity mismatch"):
        _attribute(fixture, observed=observed)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("drawing_id", True),
        ("drawing_id", 12081.0),
        ("drawing_number", False),
        ("drawing_number", 4991.0),
    ],
)
def test_observed_numeric_identity_rejects_bool_and_float(
    field: str,
    value: object,
) -> None:
    fixture = _fixture_4991()
    observed = replace(fixture.identity, **{field: value})

    with pytest.raises(AttributionIntegrityError, match=f"observed {field}"):
        _attribute(fixture, observed=observed)


@pytest.mark.parametrize(("field", "value"), [("plan_id", 1), ("package_id", 1)])
def test_observed_string_identity_requires_exact_string_type(
    field: str,
    value: object,
) -> None:
    fixture = _fixture_4991()
    observed = replace(fixture.identity, **{field: value})

    with pytest.raises(AttributionIntegrityError, match=f"observed {field}"):
        _attribute(fixture, observed=observed)


def test_coupon_mutation_fails_with_unchanged_hash_metadata() -> None:
    fixture = _fixture_4991()
    mutated = copy.deepcopy(fixture.coupons)
    mutated[0] = "2" + mutated[0][1:]

    with pytest.raises(AttributionIntegrityError, match="coupon sequence"):
        _attribute(replace(fixture, coupons=mutated))


def test_package_payload_mutation_fails_with_unchanged_hash_metadata() -> None:
    fixture = _fixture_4991()
    original = fixture.coupons[0]
    replacement = "2" + original[1:]
    mutated_payload = fixture.package_payload.replace(
        original.encode("utf-8"),
        replacement.encode("utf-8"),
        1,
    )
    mutated_coupons = list(fixture.coupons)
    mutated_coupons[0] = replacement

    with pytest.raises(AttributionIntegrityError, match="package content SHA-256"):
        _attribute(
            replace(
                fixture,
                coupons=mutated_coupons,
                package_payload=mutated_payload,
            )
        )


def test_frozen_odds_mutation_fails_with_unchanged_hash_metadata() -> None:
    fixture = _fixture_4991()
    events = copy.deepcopy(fixture.events)
    events[0]["bk"]["1"] += 1  # type: ignore[index,operator]

    with pytest.raises(AttributionIntegrityError, match="frozen probability"):
        _attribute(replace(fixture, events=events))


def test_final_input_mutation_fails_with_unchanged_declared_hash() -> None:
    fixture = _fixture_4991()
    document = json.loads(fixture.final_input_payload)
    document["payload"]["data"]["events"][0]["quotes"]["bk_win_1"] += 1
    mutated = _canonical_bytes(document) + b"\n"

    with pytest.raises(AttributionIntegrityError, match="final input content SHA-256"):
        _attribute(replace(fixture, final_input_payload=mutated))


def test_settled_result_mutation_fails_with_unchanged_hash_metadata() -> None:
    fixture = _fixture_4991()
    settled = json.loads(fixture.settled_result_payload)
    settled[0]["score"] = "9 : 9"

    with pytest.raises(AttributionIntegrityError, match="settled result content"):
        _attribute(replace(fixture, settled_result_payload=_canonical_bytes(settled)))


def test_tied_best_attribution_is_stable_when_package_rows_reorder() -> None:
    first = _attribute(_synthetic_fixture(["X11", "1X1"]))
    second = _attribute(_synthetic_fixture(["1X1", "X11"]))

    assert first["best_coupon_indices"] == [0, 1]
    assert second["best_coupon_indices"] == [0, 1]
    assert first["missed_positions"] == second["missed_positions"] == [2]
    assert first["all_best_missed_position_sets"] == [[1], [2]]
    assert second["all_best_missed_position_sets"] == [[1], [2]]
    for report in (first, second):
        assert "best_coupon_signature" not in report
        assert "best_coupon_signatures" not in report
        assert "best_coupon_summaries" not in report
        assert all("best_coupon_outcome" not in row for row in report["events"])


def test_void_is_excluded_from_denominator_and_joint_miss_analysis() -> None:
    fixture = _synthetic_fixture(["111", "X11"], results=("VOID", "1", "1"))

    result = _attribute(fixture)
    first = result["events"][0]

    assert result["hit_denominator"] == 2
    assert result["best_hits"] == 2
    assert result["missed_positions"] == []
    assert first["void"] is True
    assert first["miss"] is False
    assert first["actual_outcome_present"] is None
    assert first["actual_bk_rank"] is None


def test_missing_result_fails_closed_unless_void_is_explicit() -> None:
    fixture = _fixture_4991()
    events = copy.deepcopy(fixture.events)
    events[0]["result"] = None

    with pytest.raises(AttributionIntegrityError, match="unresolved result"):
        _attribute(replace(fixture, events=events))


def test_result_is_deterministic_json_serializable_and_does_not_mutate() -> None:
    fixture = _fixture_4991()
    coupons_before = copy.deepcopy(fixture.coupons)
    events_before = copy.deepcopy(fixture.events)

    first = _attribute(fixture)
    second = _attribute(fixture)

    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert fixture.coupons == coupons_before
    assert fixture.events == events_before


def test_artifact_report_status_only_cancelled_remains_pending() -> None:
    fixture = _synthetic_fixture(["111", "X11"])
    settled_events = json.loads(fixture.settled_result_payload)
    settled_events[0].update(
        result=None,
        result_status="cancelled",
        score=None,
        void_source=_VOID_SOURCE,
    )
    archive_payload, settled_payload, operator_payload = _artifact_payloads(
        fixture,
        settled_events=settled_events,
    )

    report = build_post_draw_attribution_report(
        settled_drawing_payload=settled_payload,
        package_payload=fixture.package_payload,
        package_archive_payload=archive_payload,
        final_input_payload=fixture.final_input_payload,
        operator_result_payload=operator_payload,
    )

    assert report["status"] == PENDING_RESULTS
    assert report["analysis_only_label"] == ANALYSIS_ONLY_LABEL
    assert report["hit_denominator"] is None
    assert report["best_hits"] is None
    assert report["result_classification"]["cancelled_event_orders"] == [1]
    assert report["result_classification"]["excluded_event_orders"] == []
    assert report["result_classification"]["pending_event_orders"] == [1]
    first = report["events"][0]
    assert first["result_classification"] == "cancelled"
    assert first["terminal_result"] is False
    assert first["excluded_from_hit_denominator"] is False
    assert first["reviewed_void_source"] is None


def test_artifact_report_explicit_reviewed_cancelled_is_excluded() -> None:
    fixture = _synthetic_fixture(["111", "X11"])
    settled_events = json.loads(fixture.settled_result_payload)
    settled_events[0].update(
        result="*",
        result_status="cancelled",
        score="",
        void_source=_VOID_SOURCE,
    )
    archive_payload, settled_payload, operator_payload = _artifact_payloads(
        fixture,
        settled_events=settled_events,
    )

    report = build_post_draw_attribution_report(
        settled_drawing_payload=settled_payload,
        package_payload=fixture.package_payload,
        package_archive_payload=archive_payload,
        final_input_payload=fixture.final_input_payload,
        operator_result_payload=operator_payload,
    )

    assert report["status"] == ATTRIBUTION_COMPLETE
    assert report["hit_denominator"] == 2
    assert report["result_classification"]["cancelled_event_orders"] == [1]
    assert report["result_classification"]["excluded_event_orders"] == [1]
    first = report["events"][0]
    assert first["actual_outcome"] == "VOID"
    assert first["terminal_result"] is True
    assert first["excluded_from_hit_denominator"] is True
    assert first["reviewed_void_source"] == _VOID_SOURCE


def test_artifact_report_postponed_without_void_remains_pending() -> None:
    fixture = _synthetic_fixture(["111", "X11"])
    settled_events = json.loads(fixture.settled_result_payload)
    settled_events[0].update(
        result="",
        result_status="postponed",
        score="",
        void_source=_VOID_SOURCE,
    )
    archive_payload, settled_payload, operator_payload = _artifact_payloads(
        fixture,
        settled_events=settled_events,
    )

    report = build_post_draw_attribution_report(
        settled_drawing_payload=settled_payload,
        package_payload=fixture.package_payload,
        package_archive_payload=archive_payload,
        final_input_payload=fixture.final_input_payload,
        operator_result_payload=operator_payload,
    )

    assert report["status"] == PENDING_RESULTS
    assert report["best_hits"] is None
    assert report["hit_denominator"] is None
    assert report["result_classification"]["postponed_event_orders"] == [1]
    assert report["result_classification"]["pending_event_orders"] == [1]
    assert report["result_classification"]["excluded_event_orders"] == []
    first = report["events"][0]
    assert first["result_classification"] == "postponed"
    assert first["terminal_result"] is False
    assert first["excluded_from_hit_denominator"] is False


def test_artifact_report_explicit_postponed_without_review_is_pending() -> None:
    fixture = _synthetic_fixture(["111", "X11"])
    settled_events = json.loads(fixture.settled_result_payload)
    settled_events[0].update(result="*", result_status="postponed", score="")
    archive_payload, settled_payload, operator_payload = _artifact_payloads(
        fixture,
        settled_events=settled_events,
    )

    report = build_post_draw_attribution_report(
        settled_drawing_payload=settled_payload,
        package_payload=fixture.package_payload,
        package_archive_payload=archive_payload,
        final_input_payload=fixture.final_input_payload,
        operator_result_payload=operator_payload,
    )

    assert report["status"] == PENDING_RESULTS
    assert report["result_classification"]["postponed_event_orders"] == [1]
    assert report["result_classification"]["excluded_event_orders"] == []
    assert report["result_classification"]["pending_event_orders"] == [1]


def test_artifact_report_explicit_reviewed_postponed_void_is_excluded() -> None:
    fixture = _synthetic_fixture(["111", "X11"])
    settled_events = json.loads(fixture.settled_result_payload)
    settled_events[0].update(
        result="*",
        result_status="postponed",
        score="",
        void_source=_VOID_SOURCE,
    )
    archive_payload, settled_payload, operator_payload = _artifact_payloads(
        fixture,
        settled_events=settled_events,
    )

    report = build_post_draw_attribution_report(
        settled_drawing_payload=settled_payload,
        package_payload=fixture.package_payload,
        package_archive_payload=archive_payload,
        final_input_payload=fixture.final_input_payload,
        operator_result_payload=operator_payload,
    )

    assert report["status"] == ATTRIBUTION_COMPLETE
    assert report["result_classification"]["postponed_event_orders"] == [1]
    assert report["result_classification"]["excluded_event_orders"] == [1]
    assert report["result_classification"]["pending_event_orders"] == []
    assert report["events"][0]["reviewed_void_source"] == _VOID_SOURCE


def test_artifact_report_missing_result_without_status_is_pending() -> None:
    fixture = _synthetic_fixture(["111", "X11"])
    settled_events = json.loads(fixture.settled_result_payload)
    settled_events[0].update(result=None, result_status=None, score=None)
    archive_payload, settled_payload, operator_payload = _artifact_payloads(
        fixture,
        settled_events=settled_events,
    )

    report = build_post_draw_attribution_report(
        settled_drawing_payload=settled_payload,
        package_payload=fixture.package_payload,
        package_archive_payload=archive_payload,
        final_input_payload=fixture.final_input_payload,
        operator_result_payload=operator_payload,
    )

    assert report["status"] == PENDING_RESULTS
    assert report["result_classification"]["pending_event_orders"] == [1]
    assert report["result_classification"]["postponed_event_orders"] == []
    assert report["events"][0]["result_classification"] == "pending"


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"decision": "NO BET", "actionable": False}, "operator PLAY provenance"),
        ({"source_package_sha256": "b" * 64}, "package/archive identity"),
    ],
)
def test_artifact_report_requires_hash_bound_scheduler_operator_play(
    changes: dict[str, object],
    message: str,
) -> None:
    fixture = _synthetic_fixture(["111", "X11"])
    archive_payload, settled_payload, operator_payload = _artifact_payloads(fixture)
    operator_payload = _updated_operator_payload(operator_payload, **changes)

    with pytest.raises(AttributionIntegrityError, match=message):
        build_post_draw_attribution_report(
            settled_drawing_payload=settled_payload,
            package_payload=fixture.package_payload,
            package_archive_payload=archive_payload,
            final_input_payload=fixture.final_input_payload,
            operator_result_payload=operator_payload,
        )


def test_artifact_report_exposes_aggregate_attribution_only(tmp_path: Path) -> None:
    fixture = _synthetic_fixture(["111", "X11"])
    archive_payload, settled_payload, operator_payload = _artifact_payloads(fixture)
    report = build_post_draw_attribution_report(
        settled_drawing_payload=settled_payload,
        package_payload=fixture.package_payload,
        package_archive_payload=archive_payload,
        final_input_payload=fixture.final_input_payload,
        operator_result_payload=operator_payload,
    )
    paths = write_post_draw_attribution_reports(report, output_dir=tmp_path)

    assert report["attribution_scope"] == "aggregate_only"
    serialized = "\n".join(
        (
            paths.json_path.read_text(encoding="utf-8"),
            paths.csv_path.read_text(encoding="utf-8"),
            paths.markdown_path.read_text(encoding="utf-8"),
        )
    )
    for forbidden in (
        *fixture.coupons,
        "best_coupon_signature",
        "best_coupon_outcome",
        "coupon_signature",
    ):
        assert forbidden not in serialized
    assert "best_coupon_rank" not in report
    assert "best_coupon_indices" not in report


def test_generate_reports_writes_deterministic_json_csv_and_markdown(
    tmp_path: Path,
) -> None:
    fixture = _synthetic_fixture(["111", "X11"])
    package_dir, operator_path, settled_path, output_dir = _write_artifact_files(
        tmp_path,
        fixture,
    )

    first, paths = generate_post_draw_attribution_reports(
        settled_drawing_file=settled_path,
        package_dir=package_dir,
        operator_result_file=operator_path,
        output_dir=output_dir,
    )
    report_paths = (
        paths.json_path,
        paths.csv_path,
        paths.markdown_path,
        paths.manifest_path,
    )
    before = {path: path.read_bytes() for path in report_paths}
    second, repeated_paths = generate_post_draw_attribution_reports(
        settled_drawing_file=settled_path,
        package_dir=package_dir,
        operator_result_file=operator_path,
        output_dir=output_dir,
    )

    assert first == second
    assert repeated_paths == paths
    assert {path: path.read_bytes() for path in report_paths} == before
    assert len({path.parent for path in report_paths}) == 1
    assert paths.json_path.parent.name == paths.generation_sha256
    assert json.loads(paths.json_path.read_text()) == first
    assert paths.csv_path.read_text().startswith("position,event_id,home_team")
    markdown = paths.markdown_path.read_text()
    assert ANALYSIS_ONLY_LABEL in markdown
    assert "Cancelled/VOID events are excluded" in markdown
    manifest = json.loads(paths.manifest_path.read_text(encoding="utf-8"))
    assert manifest["generation_sha256"] == paths.generation_sha256
    assert manifest["files"] == {
        path.name: _sha256(path.read_bytes()) for path in report_paths[:3]
    }


def test_report_bundle_failure_does_not_publish_a_mixed_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _synthetic_fixture(["111", "X11"])
    package_dir, operator_path, settled_path, output_dir = _write_artifact_files(
        tmp_path,
        fixture,
    )
    report, paths = generate_post_draw_attribution_reports(
        settled_drawing_file=settled_path,
        package_dir=package_dir,
        operator_result_file=operator_path,
        output_dir=output_dir,
    )
    original_bytes = {
        path: path.read_bytes()
        for path in (
            paths.json_path,
            paths.csv_path,
            paths.markdown_path,
            paths.manifest_path,
        )
    }
    changed_report = copy.deepcopy(report)
    changed_report["settled_drawing_sha256"] = "b" * 64
    original_writer = attribution_module._write_staged_report_file

    def fail_on_csv(path: Path, payload: bytes) -> None:
        if path.suffix == ".csv":
            raise OSError("injected report write failure")
        original_writer(path, payload)

    monkeypatch.setattr(
        attribution_module,
        "_write_staged_report_file",
        fail_on_csv,
    )

    with pytest.raises(OSError, match="injected report write failure"):
        write_post_draw_attribution_reports(changed_report, output_dir=output_dir)

    generations = output_dir / "generations"
    assert [path.name for path in generations.iterdir()] == [
        paths.generation_sha256
    ]
    assert {path: path.read_bytes() for path in original_bytes} == original_bytes


def test_post_draw_attribution_cli_reports_pending_with_exit_two(
    tmp_path: Path,
) -> None:
    fixture = _synthetic_fixture(["111", "X11"])
    settled_events = json.loads(fixture.settled_result_payload)
    settled_events[2].update(result=None, result_status=None, score=None)
    package_dir, operator_path, settled_path, output_dir = _write_artifact_files(
        tmp_path,
        fixture,
        settled_events=settled_events,
    )

    result = CliRunner().invoke(
        app,
        [
            "post-draw-attribution",
            "--settled-drawing",
            str(settled_path),
            "--package-dir",
            str(package_dir),
            "--operator-result",
            str(operator_path),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 2, result.stdout
    summary = json.loads(result.stdout)
    assert summary["status"] == PENDING_RESULTS
    assert summary["pending_event_orders"] == [3]
    report = json.loads(Path(summary["reports"]["json"]).read_text(encoding="utf-8"))
    assert report["status"] == PENDING_RESULTS
